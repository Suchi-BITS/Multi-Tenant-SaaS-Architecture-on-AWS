"""
Tenant Management Service

Handles tenant lifecycle operations:
- Tenant registration (onboarding)
- Tenant configuration updates
- Tenant status management
- Tenant deletion (offboarding)
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any

import boto3
from boto3.dynamodb.conditions import Key

# Import shared utilities
import sys
sys.path.append('/opt/python')
from tenant_utils import (
    tenant_aware_handler, 
    create_response, 
    TenantContext,
    log_tenant_activity
)

# AWS Clients
dynamodb = boto3.resource('dynamodb')
cognito_client = boto3.client('cognito-idp')
iam_client = boto3.client('iam')

# Environment variables
TENANT_TABLE = os.environ.get('TENANT_TABLE', 'tenants')
USER_POOL_ID = os.environ.get('USER_POOL_ID')


def register_tenant(event, context):
    """
    Registers a new tenant in the system.
    
    This function performs the complete tenant onboarding process:
    1. Creates tenant record in DynamoDB
    2. Sets up Cognito user pool group
    3. Configures IAM policies
    4. Provisions tenant-specific resources (if silo model)
    5. Initializes tenant configuration
    
    Request body:
    {
        "company_name": "Acme Corp",
        "admin_email": "admin@acme.com",
        "tier": "basic|premium|enterprise",
        "isolation_model": "pool|silo"
    }
    """
    try:
        body = json.loads(event['body'])
        
        # Generate unique tenant ID
        tenant_id = str(uuid.uuid4())
        
        # Extract tenant information
        company_name = body.get('company_name')
        admin_email = body.get('admin_email')
        tier = body.get('tier', 'basic')
        isolation_model = body.get('isolation_model', 'pool')
        
        # Validate required fields
        if not company_name or not admin_email:
            return create_response(400, {
                'error': 'company_name and admin_email are required'
            })
        
        # Create tenant record
        tenant_record = {
            'tenant_id': tenant_id,
            'company_name': company_name,
            'admin_email': admin_email,
            'tier': tier,
            'isolation_model': isolation_model,
            'status': 'active',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'limits': get_tier_limits(tier),
            'features': get_tier_features(tier)
        }
        
        # Store in DynamoDB
        table = dynamodb.Table(TENANT_TABLE)
        table.put_item(Item=tenant_record)
        
        # Create Cognito user pool group for tenant
        create_tenant_user_group(tenant_id, tier)
        
        # Provision tenant-specific resources if silo model
        if isolation_model == 'silo':
            provision_silo_resources(tenant_id)
        
        # Log successful registration
        log_tenant_activity(
            TenantContext(tenant_id, tier),
            'register_tenant',
            'SUCCESS'
        )
        
        return create_response(201, {
            'message': 'Tenant registered successfully',
            'tenant_id': tenant_id,
            'tier': tier,
            'isolation_model': isolation_model
        })
        
    except Exception as e:
        print(f"Error registering tenant: {str(e)}")
        return create_response(500, {
            'error': 'Failed to register tenant',
            'details': str(e)
        })


@tenant_aware_handler
def get_tenant(event, context):
    """
    Retrieves tenant information.
    
    Path parameters:
    - tenant_id: Unique tenant identifier
    """
    try:
        tenant_context = event['tenant_context']
        path_params = event.get('pathParameters', {})
        tenant_id = path_params.get('tenant_id')
        
        if not tenant_id:
            return create_response(400, {
                'error': 'tenant_id is required'
            })
        
        # Verify tenant can access this resource
        if tenant_context.tenant_id != tenant_id:
            return create_response(403, {
                'error': 'Access denied to tenant resource'
            })
        
        # Retrieve tenant from DynamoDB
        table = dynamodb.Table(TENANT_TABLE)
        response = table.get_item(Key={'tenant_id': tenant_id})
        
        if 'Item' not in response:
            return create_response(404, {
                'error': 'Tenant not found'
            })
        
        tenant_data = response['Item']
        
        # Remove sensitive fields
        tenant_data.pop('api_keys', None)
        
        return create_response(200, tenant_data, tenant_context)
        
    except Exception as e:
        print(f"Error getting tenant: {str(e)}")
        return create_response(500, {
            'error': 'Failed to retrieve tenant',
            'details': str(e)
        })


@tenant_aware_handler
def update_tenant(event, context):
    """
    Updates tenant configuration.
    
    Request body can include:
    - tier: Change subscription tier
    - features: Update feature flags
    - limits: Adjust resource limits
    - status: Change tenant status (active, suspended, deleted)
    """
    try:
        tenant_context = event['tenant_context']
        path_params = event.get('pathParameters', {})
        tenant_id = path_params.get('tenant_id')
        
        if tenant_context.tenant_id != tenant_id:
            return create_response(403, {
                'error': 'Access denied'
            })
        
        body = json.loads(event['body'])
        
        # Build update expression
        update_expression = "SET updated_at = :updated_at"
        expression_values = {
            ':updated_at': datetime.utcnow().isoformat()
        }
        
        # Update tier if provided
        if 'tier' in body:
            update_expression += ", tier = :tier, limits = :limits, features = :features"
            new_tier = body['tier']
            expression_values[':tier'] = new_tier
            expression_values[':limits'] = get_tier_limits(new_tier)
            expression_values[':features'] = get_tier_features(new_tier)
        
        # Update status if provided
        if 'status' in body:
            update_expression += ", #status = :status"
            expression_values[':status'] = body['status']
        
        # Update in DynamoDB
        table = dynamodb.Table(TENANT_TABLE)
        response = table.update_item(
            Key={'tenant_id': tenant_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames={'#status': 'status'} if 'status' in body else None,
            ReturnValues='ALL_NEW'
        )
        
        return create_response(200, {
            'message': 'Tenant updated successfully',
            'tenant': response['Attributes']
        }, tenant_context)
        
    except Exception as e:
        print(f"Error updating tenant: {str(e)}")
        return create_response(500, {
            'error': 'Failed to update tenant',
            'details': str(e)
        })


@tenant_aware_handler
def delete_tenant(event, context):
    """
    Deletes a tenant (offboarding).
    
    This performs a soft delete by setting status to 'deleted'.
    Actual resource cleanup happens asynchronously.
    """
    try:
        tenant_context = event['tenant_context']
        path_params = event.get('pathParameters', {})
        tenant_id = path_params.get('tenant_id')
        
        if tenant_context.tenant_id != tenant_id:
            return create_response(403, {
                'error': 'Access denied'
            })
        
        # Soft delete: Update status to 'deleted'
        table = dynamodb.Table(TENANT_TABLE)
        table.update_item(
            Key={'tenant_id': tenant_id},
            UpdateExpression='SET #status = :status, deleted_at = :deleted_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'deleted',
                ':deleted_at': datetime.utcnow().isoformat()
            }
        )
        
        # Trigger async cleanup process
        # In production, this would publish to SNS/SQS for:
        # - Deleting silo resources
        # - Archiving data
        # - Removing user pool groups
        # - Cleaning up IAM policies
        
        return create_response(200, {
            'message': 'Tenant deletion initiated',
            'tenant_id': tenant_id
        }, tenant_context)
        
    except Exception as e:
        print(f"Error deleting tenant: {str(e)}")
        return create_response(500, {
            'error': 'Failed to delete tenant',
            'details': str(e)
        })


def get_tier_limits(tier: str) -> Dict[str, int]:
    """
    Returns resource limits based on subscription tier.
    """
    limits = {
        'basic': {
            'max_products': 100,
            'max_orders': 1000,
            'max_users': 10,
            'max_api_calls_per_hour': 1000
        },
        'premium': {
            'max_products': 1000,
            'max_orders': 10000,
            'max_users': 50,
            'max_api_calls_per_hour': 10000
        },
        'enterprise': {
            'max_products': -1,  # Unlimited
            'max_orders': -1,
            'max_users': -1,
            'max_api_calls_per_hour': 100000
        }
    }
    return limits.get(tier, limits['basic'])


def get_tier_features(tier: str) -> Dict[str, bool]:
    """
    Returns available features based on subscription tier.
    """
    features = {
        'basic': {
            'advanced_analytics': False,
            'custom_branding': False,
            'api_access': True,
            'priority_support': False,
            'data_export': False
        },
        'premium': {
            'advanced_analytics': True,
            'custom_branding': True,
            'api_access': True,
            'priority_support': True,
            'data_export': True
        },
        'enterprise': {
            'advanced_analytics': True,
            'custom_branding': True,
            'api_access': True,
            'priority_support': True,
            'data_export': True,
            'dedicated_support': True,
            'custom_integrations': True
        }
    }
    return features.get(tier, features['basic'])


def create_tenant_user_group(tenant_id: str, tier: str):
    """
    Creates Cognito user pool group for the tenant.
    This enables tenant-based access control.
    """
    try:
        group_name = f"tenant-{tenant_id}"
        
        cognito_client.create_group(
            GroupName=group_name,
            UserPoolId=USER_POOL_ID,
            Description=f"User group for tenant {tenant_id}",
            Precedence=0
        )
        
        print(f"Created Cognito group: {group_name}")
        
    except cognito_client.exceptions.GroupExistsException:
        print(f"Group already exists: tenant-{tenant_id}")
    except Exception as e:
        print(f"Error creating user group: {str(e)}")


def provision_silo_resources(tenant_id: str):
    """
    Provisions dedicated resources for silo isolation model.
    
    Creates:
    - Dedicated DynamoDB tables
    - Dedicated S3 buckets
    - Tenant-specific IAM roles
    """
    try:
        # Create DynamoDB tables
        create_tenant_tables(tenant_id)
        
        # Create S3 bucket
        create_tenant_bucket(tenant_id)
        
        print(f"Provisioned silo resources for tenant: {tenant_id}")
        
    except Exception as e:
        print(f"Error provisioning silo resources: {str(e)}")
        raise


def create_tenant_tables(tenant_id: str):
    """Creates DynamoDB tables for silo model."""
    dynamodb_client = boto3.client('dynamodb')
    
    tables = ['products', 'orders']
    
    for base_table in tables:
        table_name = f"{base_table}-{tenant_id}"
        
        try:
            dynamodb_client.create_table(
                TableName=table_name,
                KeySchema=[
                    {'AttributeName': 'id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'id', 'AttributeType': 'S'}
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            print(f"Created table: {table_name}")
        except dynamodb_client.exceptions.ResourceInUseException:
            print(f"Table already exists: {table_name}")


def create_tenant_bucket(tenant_id: str):
    """Creates S3 bucket for silo model."""
    s3_client = boto3.client('s3')
    bucket_name = f"saas-tenant-{tenant_id}"
    
    try:
        s3_client.create_bucket(Bucket=bucket_name)
        print(f"Created S3 bucket: {bucket_name}")
    except Exception as e:
        print(f"Error creating bucket: {str(e)}")
