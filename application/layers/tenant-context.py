"""
Tenant Context Layer
Provides utilities for extracting and managing tenant context in Lambda functions
"""

import json
import jwt
import os
from typing import Dict, Any, Optional
from functools import wraps

class TenantContext:
    """Manages tenant context throughout the request lifecycle"""
    
    def __init__(self, tenant_id: str, tenant_tier: str, user_id: str = None):
        self.tenant_id = tenant_id
        self.tenant_tier = tenant_tier
        self.user_id = user_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary"""
        return {
            'tenant_id': self.tenant_id,
            'tenant_tier': self.tenant_tier,
            'user_id': self.user_id
        }
    
    def __str__(self) -> str:
        return f"TenantContext(tenant_id={self.tenant_id}, tier={self.tenant_tier})"


def extract_tenant_context(event: Dict[str, Any]) -> TenantContext:
    """
    Extract tenant context from API Gateway event
    
    Args:
        event: API Gateway event
        
    Returns:
        TenantContext object
        
    Raises:
        ValueError: If tenant context cannot be extracted
    """
    try:
        # Try to get from authorizer context first
        authorizer = event.get('requestContext', {}).get('authorizer', {})
        
        if 'claims' in authorizer:
            claims = authorizer['claims']
            return TenantContext(
                tenant_id=claims.get('custom:tenant_id'),
                tenant_tier=claims.get('custom:tenant_tier', 'pool'),
                user_id=claims.get('sub')
            )
        
        # Fallback: try to extract from JWT token
        token = extract_token_from_header(event)
        if token:
            return extract_from_jwt(token)
        
        # Last resort: check headers
        headers = event.get('headers', {})
        tenant_id = headers.get('X-Tenant-Id') or headers.get('x-tenant-id')
        
        if tenant_id:
            return TenantContext(
                tenant_id=tenant_id,
                tenant_tier=headers.get('X-Tenant-Tier', 'pool')
            )
        
        raise ValueError("No tenant context found in request")
        
    except Exception as e:
        print(f"Error extracting tenant context: {str(e)}")
        raise


def extract_token_from_header(event: Dict[str, Any]) -> Optional[str]:
    """Extract JWT token from Authorization header"""
    headers = event.get('headers', {})
    auth_header = headers.get('Authorization') or headers.get('authorization')
    
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]
    
    return None


def extract_from_jwt(token: str) -> TenantContext:
    """
    Extract tenant context from JWT token
    Note: This does NOT verify the token signature - that should be done by API Gateway
    """
    try:
        # Decode without verification (verification done by API Gateway)
        decoded = jwt.decode(token, options={"verify_signature": False})
        
        return TenantContext(
            tenant_id=decoded.get('custom:tenant_id'),
            tenant_tier=decoded.get('custom:tenant_tier', 'pool'),
            user_id=decoded.get('sub')
        )
    except Exception as e:
        print(f"Error decoding JWT: {str(e)}")
        raise


def with_tenant_context(func):
    """
    Decorator to automatically inject tenant context into Lambda function
    
    Usage:
        @with_tenant_context
        def lambda_handler(event, context, tenant_context):
            print(f"Processing request for tenant: {tenant_context.tenant_id}")
    """
    @wraps(func)
    def wrapper(event, context):
        try:
            tenant_context = extract_tenant_context(event)
            return func(event, context, tenant_context)
        except ValueError as e:
            return {
                'statusCode': 401,
                'body': json.dumps({
                    'error': 'Unauthorized',
                    'message': str(e)
                })
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Internal Server Error',
                    'message': str(e)
                })
            }
    
    return wrapper


def get_database_connection_params(tenant_context: TenantContext) -> Dict[str, Any]:
    """
    Get database connection parameters based on tenant tier
    
    Args:
        tenant_context: Tenant context
        
    Returns:
        Database connection parameters
    """
    if tenant_context.tenant_tier == 'pool':
        # Shared database, use row-level security
        return {
            'database': os.environ.get('POOL_DATABASE'),
            'schema': 'public',
            'row_security_context': tenant_context.tenant_id
        }
    
    elif tenant_context.tenant_tier == 'bridge':
        # Shared database, dedicated schema
        schema_name = f"tenant_{tenant_context.tenant_id.replace('-', '_')}"
        return {
            'database': os.environ.get('BRIDGE_DATABASE'),
            'schema': schema_name,
            'row_security_context': None
        }
    
    elif tenant_context.tenant_tier == 'silo':
        # Dedicated database
        return {
            'database': f"tenant_{tenant_context.tenant_id}",
            'schema': 'public',
            'row_security_context': None
        }
    
    else:
        raise ValueError(f"Unknown tenant tier: {tenant_context.tenant_tier}")


def apply_tenant_filter(query: str, tenant_context: TenantContext) -> str:
    """
    Apply tenant filter to SQL query based on tier
    
    Args:
        query: SQL query
        tenant_context: Tenant context
        
    Returns:
        Modified query with tenant filter
    """
    if tenant_context.tenant_tier == 'pool':
        # Add WHERE clause for tenant_id
        if 'WHERE' in query.upper():
            return query.replace('WHERE', f"WHERE tenant_id = '{tenant_context.tenant_id}' AND")
        else:
            return query.rstrip(';') + f" WHERE tenant_id = '{tenant_context.tenant_id}';"
    
    # For bridge and silo, schema/database isolation handles filtering
    return query


def get_s3_prefix(tenant_context: TenantContext) -> str:
    """
    Get S3 prefix for tenant data
    
    Args:
        tenant_context: Tenant context
        
    Returns:
        S3 prefix path
    """
    return f"tenants/{tenant_context.tenant_id}/"


def validate_tenant_access(tenant_context: TenantContext, resource_tenant_id: str) -> bool:
    """
    Validate that the current tenant has access to a resource
    
    Args:
        tenant_context: Current tenant context
        resource_tenant_id: Tenant ID of the resource
        
    Returns:
        True if access is allowed, False otherwise
    """
    return tenant_context.tenant_id == resource_tenant_id


# Export main utilities
__all__ = [
    'TenantContext',
    'extract_tenant_context',
    'with_tenant_context',
    'get_database_connection_params',
    'apply_tenant_filter',
    'get_s3_prefix',
    'validate_tenant_access'
]
