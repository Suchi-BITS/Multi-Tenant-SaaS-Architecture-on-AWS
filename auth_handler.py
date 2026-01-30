"""
Authentication Service

Handles user authentication and authorization:
- User signup
- User signin
- Token refresh
- Password reset
- User management within tenant context

Uses Amazon Cognito for identity management with tenant isolation.
"""

import json
import os
import boto3
import hmac
import hashlib
import base64
from typing import Dict, Any

# Import shared utilities
import sys
sys.path.append('/opt/python')
from tenant_utils import (
    create_response,
    get_tenant_config,
    log_tenant_activity,
    TenantContext
)

# AWS clients
cognito_client = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')

# Environment variables
USER_POOL_ID = os.environ.get('USER_POOL_ID')
CLIENT_ID = os.environ.get('CLIENT_ID')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
TENANT_TABLE = os.environ.get('TENANT_TABLE', 'tenants')


def get_secret_hash(username: str) -> str:
    """
    Calculates SECRET_HASH for Cognito operations.
    Required when app client has a secret.
    """
    if not CLIENT_SECRET:
        return None
    
    message = username + CLIENT_ID
    dig = hmac.new(
        CLIENT_SECRET.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(dig).decode()


def signup(event, context):
    """
    Registers a new user within a tenant.
    
    Request body:
    {
        "email": "user@example.com",
        "password": "SecurePassword123!",
        "tenant_id": "tenant-uuid",
        "given_name": "John",
        "family_name": "Doe"
    }
    """
    try:
        body = json.loads(event['body'])
        
        email = body.get('email')
        password = body.get('password')
        tenant_id = body.get('tenant_id')
        given_name = body.get('given_name', '')
        family_name = body.get('family_name', '')
        
        # Validate required fields
        if not all([email, password, tenant_id]):
            return create_response(400, {
                'error': 'email, password, and tenant_id are required'
            })
        
        # Verify tenant exists and is active
        tenant_config = get_tenant_config(tenant_id)
        if not tenant_config or tenant_config.get('status') != 'active':
            return create_response(400, {
                'error': 'Invalid or inactive tenant'
            })
        
        # Check user limits for tenant
        tenant_tier = tenant_config.get('tier', 'basic')
        max_users = tenant_config.get('limits', {}).get('max_users', 10)
        
        # Count existing users (simplified - in production, maintain a counter)
        # This would query Cognito or a user table
        
        # Prepare user attributes
        user_attributes = [
            {'Name': 'email', 'Value': email},
            {'Name': 'custom:tenant_id', 'Value': tenant_id},
            {'Name': 'custom:tenant_tier', 'Value': tenant_tier}
        ]
        
        if given_name:
            user_attributes.append({'Name': 'given_name', 'Value': given_name})
        if family_name:
            user_attributes.append({'Name': 'family_name', 'Value': family_name})
        
        # Create user in Cognito
        signup_params = {
            'ClientId': CLIENT_ID,
            'Username': email,
            'Password': password,
            'UserAttributes': user_attributes
        }
        
        secret_hash = get_secret_hash(email)
        if secret_hash:
            signup_params['SecretHash'] = secret_hash
        
        response = cognito_client.sign_up(**signup_params)
        
        # Add user to tenant group
        try:
            cognito_client.admin_add_user_to_group(
                UserPoolId=USER_POOL_ID,
                Username=email,
                GroupName=f"tenant-{tenant_id}"
            )
        except Exception as e:
            print(f"Error adding user to group: {str(e)}")
        
        # Log activity
        log_tenant_activity(
            TenantContext(tenant_id, tenant_tier),
            'user_signup',
            'SUCCESS'
        )
        
        return create_response(200, {
            'message': 'User registered successfully',
            'user_sub': response['UserSub'],
            'user_confirmed': response.get('UserConfirmed', False)
        })
        
    except cognito_client.exceptions.UsernameExistsException:
        return create_response(400, {
            'error': 'User already exists'
        })
    except cognito_client.exceptions.InvalidPasswordException as e:
        return create_response(400, {
            'error': 'Invalid password',
            'details': str(e)
        })
    except Exception as e:
        print(f"Error during signup: {str(e)}")
        return create_response(500, {
            'error': 'Failed to register user',
            'details': str(e)
        })


def signin(event, context):
    """
    Authenticates a user and returns JWT tokens.
    
    Request body:
    {
        "email": "user@example.com",
        "password": "SecurePassword123!"
    }
    
    Returns:
    {
        "access_token": "...",
        "id_token": "...",
        "refresh_token": "...",
        "expires_in": 3600,
        "tenant_id": "...",
        "tenant_tier": "..."
    }
    """
    try:
        body = json.loads(event['body'])
        
        email = body.get('email')
        password = body.get('password')
        
        if not email or not password:
            return create_response(400, {
                'error': 'email and password are required'
            })
        
        # Prepare authentication parameters
        auth_params = {
            'USERNAME': email,
            'PASSWORD': password
        }
        
        secret_hash = get_secret_hash(email)
        if secret_hash:
            auth_params['SECRET_HASH'] = secret_hash
        
        # Authenticate with Cognito
        response = cognito_client.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters=auth_params
        )
        
        # Extract tokens
        auth_result = response['AuthenticationResult']
        
        # Decode ID token to get tenant information (simplified)
        # In production, properly decode and validate JWT
        id_token = auth_result['IdToken']
        
        # Parse tenant info from token claims
        # This is simplified - use proper JWT library like PyJWT
        import base64
        token_parts = id_token.split('.')
        payload = json.loads(base64.b64decode(token_parts[1] + '=='))
        
        tenant_id = payload.get('custom:tenant_id', '')
        tenant_tier = payload.get('custom:tenant_tier', 'basic')
        
        # Log successful signin
        log_tenant_activity(
            TenantContext(tenant_id, tenant_tier),
            'user_signin',
            'SUCCESS'
        )
        
        return create_response(200, {
            'access_token': auth_result['AccessToken'],
            'id_token': auth_result['IdToken'],
            'refresh_token': auth_result.get('RefreshToken'),
            'expires_in': auth_result['ExpiresIn'],
            'token_type': auth_result['TokenType'],
            'tenant_id': tenant_id,
            'tenant_tier': tenant_tier
        })
        
    except cognito_client.exceptions.NotAuthorizedException:
        return create_response(401, {
            'error': 'Invalid credentials'
        })
    except cognito_client.exceptions.UserNotConfirmedException:
        return create_response(400, {
            'error': 'User not confirmed. Please verify your email.'
        })
    except Exception as e:
        print(f"Error during signin: {str(e)}")
        return create_response(500, {
            'error': 'Failed to authenticate',
            'details': str(e)
        })


def refresh_token(event, context):
    """
    Refreshes access token using refresh token.
    
    Request body:
    {
        "refresh_token": "..."
    }
    """
    try:
        body = json.loads(event['body'])
        refresh_token = body.get('refresh_token')
        
        if not refresh_token:
            return create_response(400, {
                'error': 'refresh_token is required'
            })
        
        # Get username from token (simplified)
        # In production, decode refresh token to get username
        
        auth_params = {
            'REFRESH_TOKEN': refresh_token
        }
        
        response = cognito_client.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow='REFRESH_TOKEN_AUTH',
            AuthParameters=auth_params
        )
        
        auth_result = response['AuthenticationResult']
        
        return create_response(200, {
            'access_token': auth_result['AccessToken'],
            'id_token': auth_result['IdToken'],
            'expires_in': auth_result['ExpiresIn'],
            'token_type': auth_result['TokenType']
        })
        
    except cognito_client.exceptions.NotAuthorizedException:
        return create_response(401, {
            'error': 'Invalid refresh token'
        })
    except Exception as e:
        print(f"Error refreshing token: {str(e)}")
        return create_response(500, {
            'error': 'Failed to refresh token',
            'details': str(e)
        })


def signout(event, context):
    """
    Signs out a user by invalidating their tokens.
    
    Headers:
    - Authorization: Bearer <access_token>
    """
    try:
        # Extract access token from Authorization header
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return create_response(400, {
                'error': 'Authorization header with Bearer token required'
            })
        
        access_token = auth_header.split(' ')[1]
        
        # Sign out user globally
        cognito_client.global_sign_out(
            AccessToken=access_token
        )
        
        return create_response(200, {
            'message': 'Successfully signed out'
        })
        
    except cognito_client.exceptions.NotAuthorizedException:
        return create_response(401, {
            'error': 'Invalid or expired token'
        })
    except Exception as e:
        print(f"Error during signout: {str(e)}")
        return create_response(500, {
            'error': 'Failed to sign out',
            'details': str(e)
        })


def forgot_password(event, context):
    """
    Initiates password reset flow.
    
    Request body:
    {
        "email": "user@example.com"
    }
    """
    try:
        body = json.loads(event['body'])
        email = body.get('email')
        
        if not email:
            return create_response(400, {
                'error': 'email is required'
            })
        
        params = {
            'ClientId': CLIENT_ID,
            'Username': email
        }
        
        secret_hash = get_secret_hash(email)
        if secret_hash:
            params['SecretHash'] = secret_hash
        
        cognito_client.forgot_password(**params)
        
        return create_response(200, {
            'message': 'Password reset code sent to email'
        })
        
    except cognito_client.exceptions.UserNotFoundException:
        # Return success even if user doesn't exist (security best practice)
        return create_response(200, {
            'message': 'If the email exists, a reset code has been sent'
        })
    except Exception as e:
        print(f"Error in forgot password: {str(e)}")
        return create_response(500, {
            'error': 'Failed to initiate password reset',
            'details': str(e)
        })


def confirm_forgot_password(event, context):
    """
    Confirms password reset with code.
    
    Request body:
    {
        "email": "user@example.com",
        "confirmation_code": "123456",
        "new_password": "NewSecurePassword123!"
    }
    """
    try:
        body = json.loads(event['body'])
        
        email = body.get('email')
        confirmation_code = body.get('confirmation_code')
        new_password = body.get('new_password')
        
        if not all([email, confirmation_code, new_password]):
            return create_response(400, {
                'error': 'email, confirmation_code, and new_password are required'
            })
        
        params = {
            'ClientId': CLIENT_ID,
            'Username': email,
            'ConfirmationCode': confirmation_code,
            'Password': new_password
        }
        
        secret_hash = get_secret_hash(email)
        if secret_hash:
            params['SecretHash'] = secret_hash
        
        cognito_client.confirm_forgot_password(**params)
        
        return create_response(200, {
            'message': 'Password reset successfully'
        })
        
    except cognito_client.exceptions.CodeMismatchException:
        return create_response(400, {
            'error': 'Invalid confirmation code'
        })
    except cognito_client.exceptions.ExpiredCodeException:
        return create_response(400, {
            'error': 'Confirmation code has expired'
        })
    except Exception as e:
        print(f"Error confirming password reset: {str(e)}")
        return create_response(500, {
            'error': 'Failed to reset password',
            'details': str(e)
        })


def verify_email(event, context):
    """
    Verifies user email with confirmation code.
    
    Request body:
    {
        "email": "user@example.com",
        "confirmation_code": "123456"
    }
    """
    try:
        body = json.loads(event['body'])
        
        email = body.get('email')
        confirmation_code = body.get('confirmation_code')
        
        if not email or not confirmation_code:
            return create_response(400, {
                'error': 'email and confirmation_code are required'
            })
        
        params = {
            'ClientId': CLIENT_ID,
            'Username': email,
            'ConfirmationCode': confirmation_code
        }
        
        secret_hash = get_secret_hash(email)
        if secret_hash:
            params['SecretHash'] = secret_hash
        
        cognito_client.confirm_sign_up(**params)
        
        return create_response(200, {
            'message': 'Email verified successfully'
        })
        
    except cognito_client.exceptions.CodeMismatchException:
        return create_response(400, {
            'error': 'Invalid confirmation code'
        })
    except Exception as e:
        print(f"Error verifying email: {str(e)}")
        return create_response(500, {
            'error': 'Failed to verify email',
            'details': str(e)
        })
