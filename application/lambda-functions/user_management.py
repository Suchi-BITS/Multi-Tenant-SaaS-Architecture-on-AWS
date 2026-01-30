"""
User Management Lambda Function
Handles CRUD operations for users in the multi-tenant SaaS application
"""

import json
import os
import boto3
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import bcrypt

# Import tenant context from layer
from tenant_context import with_tenant_context, TenantContext, get_database_connection_params

# AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')
cognito = boto3.client('cognito-idp')

# Environment variables
USER_POOL_ID = os.environ.get('USER_POOL_ID')


@with_tenant_context
def lambda_handler(event: Dict[str, Any], context: Any, tenant_context: TenantContext) -> Dict[str, Any]:
    """
    Main Lambda handler for user management
    
    Routes:
        GET /users - List all users
        GET /users/{user_id} - Get specific user
        POST /users - Create new user
        PUT /users/{user_id} - Update user
        DELETE /users/{user_id} - Delete user
    """
    
    http_method = event.get('httpMethod')
    path_parameters = event.get('pathParameters') or {}
    user_id = path_parameters.get('user_id')
    
    try:
        if http_method == 'GET':
            if user_id:
                return get_user(user_id, tenant_context)
            else:
                return list_users(event, tenant_context)
                
        elif http_method == 'POST':
            return create_user(event, tenant_context)
            
        elif http_method == 'PUT' and user_id:
            return update_user(user_id, event, tenant_context)
            
        elif http_method == 'DELETE' and user_id:
            return delete_user(user_id, tenant_context)
            
        else:
            return create_response(405, {'error': 'Method not allowed'})
            
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return create_response(500, {
            'error': 'Internal server error',
            'details': str(e)
        })


def list_users(event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """List all users for the tenant"""
    
    query_params = event.get('queryStringParameters') or {}
    limit = int(query_params.get('limit', 20))
    offset = int(query_params.get('offset', 0))
    role = query_params.get('role')
    status = query_params.get('status')
    
    # Build query
    query = "SELECT user_id, email, name, role, status, created_at FROM users WHERE 1=1"
    params = []
    
    if tenant_context.tenant_tier == 'pool':
        query += " AND tenant_id = %s"
        params.append(tenant_context.tenant_id)
    
    if role:
        query += " AND role = %s"
        params.append(role)
    
    if status:
        query += " AND status = %s"
        params.append(status)
    
    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    # Execute query
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, tuple(params))
        users = cursor.fetchall()
        
        # Convert to dict
        user_list = [
            {
                'user_id': str(row[0]),
                'email': row[1],
                'name': row[2],
                'role': row[3],
                'status': row[4],
                'created_at': row[5].isoformat() if row[5] else None
            }
            for row in users
        ]
        
        # Get total count
        count_query = "SELECT COUNT(*) FROM users WHERE 1=1"
        count_params = []
        
        if tenant_context.tenant_tier == 'pool':
            count_query += " AND tenant_id = %s"
            count_params.append(tenant_context.tenant_id)
        
        cursor.execute(count_query, tuple(count_params))
        total = cursor.fetchone()[0]
        
        return create_response(200, {
            'users': user_list,
            'total': total,
            'limit': limit,
            'offset': offset
        })
        
    finally:
        cursor.close()
        connection.close()


def get_user(user_id: str, tenant_context: TenantContext) -> Dict[str, Any]:
    """Get specific user by ID"""
    
    query = """
        SELECT user_id, email, name, role, status, last_login, created_at, updated_at
        FROM users 
        WHERE user_id = %s
    """
    params = [user_id]
    
    if tenant_context.tenant_tier == 'pool':
        query += " AND tenant_id = %s"
        params.append(tenant_context.tenant_id)
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        
        if not row:
            return create_response(404, {'error': 'User not found'})
        
        user = {
            'user_id': str(row[0]),
            'email': row[1],
            'name': row[2],
            'role': row[3],
            'status': row[4],
            'last_login': row[5].isoformat() if row[5] else None,
            'created_at': row[6].isoformat() if row[6] else None,
            'updated_at': row[7].isoformat() if row[7] else None
        }
        
        return create_response(200, user)
        
    finally:
        cursor.close()
        connection.close()


def create_user(event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """Create new user"""
    
    body = json.loads(event.get('body', '{}'))
    
    # Validate required fields
    required_fields = ['email', 'name', 'password']
    missing_fields = [field for field in required_fields if field not in body]
    
    if missing_fields:
        return create_response(400, {
            'error': f'Missing required fields: {", ".join(missing_fields)}'
        })
    
    email = body['email']
    name = body['name']
    password = body['password']
    role = body.get('role', 'user')
    
    # Hash password
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    user_id = str(uuid.uuid4())
    
    # Insert into database
    if tenant_context.tenant_tier == 'pool':
        query = """
            INSERT INTO users (user_id, tenant_id, email, name, password_hash, role)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING user_id, email, name, role, created_at
        """
        params = (user_id, tenant_context.tenant_id, email, name, password_hash, role)
    else:
        query = """
            INSERT INTO users (user_id, email, name, password_hash, role)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING user_id, email, name, role, created_at
        """
        params = (user_id, email, name, password_hash, role)
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, params)
        connection.commit()
        
        row = cursor.fetchone()
        
        # Create user in Cognito
        try:
            cognito.admin_create_user(
                UserPoolId=USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'true'},
                    {'Name': 'custom:tenant_id', 'Value': tenant_context.tenant_id},
                    {'Name': 'custom:user_id', 'Value': user_id}
                ],
                TemporaryPassword=password,
                DesiredDeliveryMediums=['EMAIL']
            )
        except Exception as e:
            print(f"Error creating Cognito user: {str(e)}")
            # Continue even if Cognito creation fails
        
        user = {
            'user_id': str(row[0]),
            'email': row[1],
            'name': row[2],
            'role': row[3],
            'created_at': row[4].isoformat() if row[4] else None
        }
        
        return create_response(201, {
            'message': 'User created successfully',
            'user': user
        })
        
    except Exception as e:
        connection.rollback()
        if 'unique constraint' in str(e).lower():
            return create_response(409, {'error': 'User with this email already exists'})
        raise
        
    finally:
        cursor.close()
        connection.close()


def update_user(user_id: str, event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """Update existing user"""
    
    body = json.loads(event.get('body', '{}'))
    
    # Build update query dynamically
    update_fields = []
    params = []
    
    if 'name' in body:
        update_fields.append("name = %s")
        params.append(body['name'])
    
    if 'role' in body:
        update_fields.append("role = %s")
        params.append(body['role'])
    
    if 'status' in body:
        update_fields.append("status = %s")
        params.append(body['status'])
    
    if not update_fields:
        return create_response(400, {'error': 'No fields to update'})
    
    update_fields.append("updated_at = NOW()")
    
    query = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = %s"
    params.append(user_id)
    
    if tenant_context.tenant_tier == 'pool':
        query += " AND tenant_id = %s"
        params.append(tenant_context.tenant_id)
    
    query += " RETURNING user_id, email, name, role, status, updated_at"
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, tuple(params))
        connection.commit()
        
        row = cursor.fetchone()
        
        if not row:
            return create_response(404, {'error': 'User not found'})
        
        user = {
            'user_id': str(row[0]),
            'email': row[1],
            'name': row[2],
            'role': row[3],
            'status': row[4],
            'updated_at': row[5].isoformat() if row[5] else None
        }
        
        return create_response(200, {
            'message': 'User updated successfully',
            'user': user
        })
        
    finally:
        cursor.close()
        connection.close()


def delete_user(user_id: str, tenant_context: TenantContext) -> Dict[str, Any]:
    """Delete user (soft delete by setting status to 'deleted')"""
    
    query = "UPDATE users SET status = 'deleted', updated_at = NOW() WHERE user_id = %s"
    params = [user_id]
    
    if tenant_context.tenant_tier == 'pool':
        query += " AND tenant_id = %s"
        params.append(tenant_context.tenant_id)
    
    query += " RETURNING user_id"
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, tuple(params))
        connection.commit()
        
        row = cursor.fetchone()
        
        if not row:
            return create_response(404, {'error': 'User not found'})
        
        return create_response(200, {
            'message': 'User deleted successfully',
            'user_id': str(row[0])
        })
        
    finally:
        cursor.close()
        connection.close()


def get_database_connection(tenant_context: TenantContext):
    """Get database connection with tenant context"""
    import psycopg2
    
    # Get database credentials from Secrets Manager
    secret_name = os.environ.get('DB_SECRET_NAME')
    response = secrets_manager.get_secret_value(SecretId=secret_name)
    credentials = json.loads(response['SecretString'])
    
    connection = psycopg2.connect(
        host=credentials['host'],
        database=credentials['dbname'],
        user=credentials['username'],
        password=credentials['password'],
        port=credentials.get('port', 5432)
    )
    
    # Set schema for bridge/silo models
    if tenant_context.tenant_tier in ['bridge', 'silo']:
        db_params = get_database_connection_params(tenant_context)
        cursor = connection.cursor()
        cursor.execute(f"SET search_path TO {db_params['schema']}")
        cursor.close()
    
    # Set tenant context for pool model (RLS)
    if tenant_context.tenant_tier == 'pool':
        cursor = connection.cursor()
        cursor.execute(f"SET app.current_tenant = '{tenant_context.tenant_id}'")
        cursor.close()
    
    return connection


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body, default=str)
    }
