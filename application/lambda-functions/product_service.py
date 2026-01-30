"""
Product Service Lambda Function
Handles product catalog management for multi-tenant SaaS
"""

import json
import os
import uuid
from typing import Dict, Any
from decimal import Decimal

from tenant_context import with_tenant_context, TenantContext, get_database_connection_params

@with_tenant_context
def lambda_handler(event: Dict[str, Any], context: Any, tenant_context: TenantContext) -> Dict[str, Any]:
    """
    Routes:
        GET /products - List products
        GET /products/{product_id} - Get product
        POST /products - Create product
        PUT /products/{product_id} - Update product
        DELETE /products/{product_id} - Delete product
    """
    
    http_method = event.get('httpMethod')
    path_parameters = event.get('pathParameters') or {}
    product_id = path_parameters.get('product_id')
    
    try:
        if http_method == 'GET':
            if product_id:
                return get_product(product_id, tenant_context)
            else:
                return list_products(event, tenant_context)
        elif http_method == 'POST':
            return create_product(event, tenant_context)
        elif http_method == 'PUT' and product_id:
            return update_product(product_id, event, tenant_context)
        elif http_method == 'DELETE' and product_id:
            return delete_product(product_id, tenant_context)
        else:
            return create_response(405, {'error': 'Method not allowed'})
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return create_response(500, {'error': 'Internal server error', 'details': str(e)})


def list_products(event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """List products with filtering and pagination"""
    query_params = event.get('queryStringParameters') or {}
    
    limit = int(query_params.get('limit', 50))
    offset = int(query_params.get('offset', 0))
    category = query_params.get('category')
    search = query_params.get('search')
    
    query = "SELECT product_id, name, description, price, stock_quantity, category FROM products WHERE 1=1"
    params = []
    
    if tenant_context.tenant_tier == 'pool':
        query += " AND tenant_id = %s"
        params.append(tenant_context.tenant_id)
    
    if category:
        query += " AND category = %s"
        params.append(category)
    
    if search:
        query += " AND (name ILIKE %s OR description ILIKE %s)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term])
    
    query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, tuple(params))
        products = [
            {
                'product_id': str(row[0]),
                'name': row[1],
                'description': row[2],
                'price': float(row[3]),
                'stock_quantity': row[4],
                'category': row[5]
            }
            for row in cursor.fetchall()
        ]
        
        return create_response(200, {'products': products, 'total': len(products)})
    finally:
        cursor.close()
        connection.close()


def create_product(event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """Create new product"""
    body = json.loads(event.get('body', '{}'))
    
    required_fields = ['name', 'price']
    if missing := [f for f in required_fields if f not in body]:
        return create_response(400, {'error': f'Missing fields: {", ".join(missing)}'})
    
    product_id = str(uuid.uuid4())
    
    if tenant_context.tenant_tier == 'pool':
        query = """
            INSERT INTO products (product_id, tenant_id, name, description, price, stock_quantity, category)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING product_id, name, price, created_at
        """
        params = (product_id, tenant_context.tenant_id, body['name'], 
                 body.get('description'), body['price'], 
                 body.get('stock_quantity', 0), body.get('category'))
    else:
        query = """
            INSERT INTO products (product_id, name, description, price, stock_quantity, category)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING product_id, name, price, created_at
        """
        params = (product_id, body['name'], body.get('description'), 
                 body['price'], body.get('stock_quantity', 0), body.get('category'))
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, params)
        connection.commit()
        row = cursor.fetchone()
        
        return create_response(201, {
            'message': 'Product created',
            'product': {
                'product_id': str(row[0]),
                'name': row[1],
                'price': float(row[2]),
                'created_at': row[3].isoformat()
            }
        })
    finally:
        cursor.close()
        connection.close()


def get_database_connection(tenant_context):
    """Get database connection with proper tenant context"""
    import psycopg2
    import boto3
    
    secrets_manager = boto3.client('secretsmanager')
    secret_name = os.environ.get('DB_SECRET_NAME')
    response = secrets_manager.get_secret_value(SecretId=secret_name)
    creds = json.loads(response['SecretString'])
    
    conn = psycopg2.connect(
        host=creds['host'],
        database=creds['dbname'],
        user=creds['username'],
        password=creds['password']
    )
    
    if tenant_context.tenant_tier in ['bridge', 'silo']:
        db_params = get_database_connection_params(tenant_context)
        cursor = conn.cursor()
        cursor.execute(f"SET search_path TO {db_params['schema']}")
        cursor.close()
    elif tenant_context.tenant_tier == 'pool':
        cursor = conn.cursor()
        cursor.execute(f"SET app.current_tenant = '{tenant_context.tenant_id}'")
        cursor.close()
    
    return conn


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body, default=str)
    }


def get_product(product_id: str, tenant_context: TenantContext) -> Dict[str, Any]:
    """Get single product"""
    pass  # Implementation similar to get_user


def update_product(product_id: str, event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """Update product"""
    pass  # Implementation similar to update_user


def delete_product(product_id: str, tenant_context: TenantContext) -> Dict[str, Any]:
    """Delete product"""
    pass  # Implementation similar to delete_user
