"""
Order Service Lambda Function
Handles order management for multi-tenant SaaS
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List
from decimal import Decimal

from tenant_context import with_tenant_context, TenantContext

@with_tenant_context
def lambda_handler(event: Dict[str, Any], context: Any, tenant_context: TenantContext) -> Dict[str, Any]:
    """
    Routes:
        GET /orders - List orders
        GET /orders/{order_id} - Get order
        POST /orders - Create order
        PUT /orders/{order_id} - Update order status
    """
    
    http_method = event.get('httpMethod')
    path_parameters = event.get('pathParameters') or {}
    order_id = path_parameters.get('order_id')
    
    try:
        if http_method == 'GET':
            if order_id:
                return get_order(order_id, tenant_context)
            else:
                return list_orders(event, tenant_context)
        elif http_method == 'POST':
            return create_order(event, tenant_context)
        elif http_method == 'PUT' and order_id:
            return update_order_status(order_id, event, tenant_context)
        else:
            return create_response(405, {'error': 'Method not allowed'})
            
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': 'Internal server error', 'details': str(e)})


def list_orders(event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """List orders with filtering and pagination"""
    query_params = event.get('queryStringParameters') or {}
    
    limit = int(query_params.get('limit', 20))
    offset = int(query_params.get('offset', 0))
    status = query_params.get('status')
    user_id = query_params.get('user_id')
    
    query = """
        SELECT o.order_id, o.user_id, o.order_number, o.total_amount, 
               o.status, o.created_at, u.email, u.name
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE 1=1
    """
    params = []
    
    if tenant_context.tenant_tier == 'pool':
        query += " AND o.tenant_id = %s"
        params.append(tenant_context.tenant_id)
    
    if status:
        query += " AND o.status = %s"
        params.append(status)
    
    if user_id:
        query += " AND o.user_id = %s"
        params.append(user_id)
    
    query += " ORDER BY o.created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, tuple(params))
        orders = [
            {
                'order_id': str(row[0]),
                'user_id': str(row[1]),
                'order_number': row[2],
                'total_amount': float(row[3]),
                'status': row[4],
                'created_at': row[5].isoformat(),
                'user_email': row[6],
                'user_name': row[7]
            }
            for row in cursor.fetchall()
        ]
        
        return create_response(200, {'orders': orders, 'total': len(orders)})
    finally:
        cursor.close()
        connection.close()


def get_order(order_id: str, tenant_context: TenantContext) -> Dict[str, Any]:
    """Get order with items"""
    query = """
        SELECT o.order_id, o.user_id, o.order_number, o.total_amount, 
               o.tax_amount, o.shipping_amount, o.status, o.created_at,
               u.email, u.name
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE o.order_id = %s
    """
    params = [order_id]
    
    if tenant_context.tenant_tier == 'pool':
        query += " AND o.tenant_id = %s"
        params.append(tenant_context.tenant_id)
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        
        if not row:
            return create_response(404, {'error': 'Order not found'})
        
        order = {
            'order_id': str(row[0]),
            'user_id': str(row[1]),
            'order_number': row[2],
            'total_amount': float(row[3]),
            'tax_amount': float(row[4]) if row[4] else 0,
            'shipping_amount': float(row[5]) if row[5] else 0,
            'status': row[6],
            'created_at': row[7].isoformat(),
            'user': {
                'email': row[8],
                'name': row[9]
            }
        }
        
        # Get order items
        items_query = """
            SELECT oi.order_item_id, oi.product_id, oi.quantity, 
                   oi.unit_price, oi.subtotal, p.name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            WHERE oi.order_id = %s
        """
        items_params = [order_id]
        
        if tenant_context.tenant_tier == 'pool':
            items_query += " AND oi.tenant_id = %s"
            items_params.append(tenant_context.tenant_id)
        
        cursor.execute(items_query, tuple(items_params))
        
        order['items'] = [
            {
                'order_item_id': str(row[0]),
                'product_id': str(row[1]),
                'quantity': row[2],
                'unit_price': float(row[3]),
                'subtotal': float(row[4]),
                'product_name': row[5]
            }
            for row in cursor.fetchall()
        ]
        
        return create_response(200, order)
        
    finally:
        cursor.close()
        connection.close()


def create_order(event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """Create new order with items"""
    body = json.loads(event.get('body', '{}'))
    
    required_fields = ['user_id', 'items']
    if missing := [f for f in required_fields if f not in body]:
        return create_response(400, {'error': f'Missing fields: {", ".join(missing)}'})
    
    if not body['items']:
        return create_response(400, {'error': 'Order must have at least one item'})
    
    user_id = body['user_id']
    items = body['items']
    shipping_address = body.get('shipping_address')
    billing_address = body.get('billing_address')
    
    # Calculate totals
    subtotal = sum(Decimal(str(item['unit_price'])) * item['quantity'] for item in items)
    tax_amount = subtotal * Decimal('0.1')  # 10% tax
    shipping_amount = Decimal('10.00')  # Flat shipping
    total_amount = subtotal + tax_amount + shipping_amount
    
    order_id = str(uuid.uuid4())
    order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        # Insert order
        if tenant_context.tenant_tier == 'pool':
            order_query = """
                INSERT INTO orders (
                    order_id, tenant_id, user_id, order_number, 
                    total_amount, tax_amount, shipping_amount, status,
                    shipping_address, billing_address
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING order_id, order_number, total_amount, created_at
            """
            order_params = (
                order_id, tenant_context.tenant_id, user_id, order_number,
                float(total_amount), float(tax_amount), float(shipping_amount), 'pending',
                json.dumps(shipping_address), json.dumps(billing_address)
            )
        else:
            order_query = """
                INSERT INTO orders (
                    order_id, user_id, order_number, total_amount, 
                    tax_amount, shipping_amount, status,
                    shipping_address, billing_address
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING order_id, order_number, total_amount, created_at
            """
            order_params = (
                order_id, user_id, order_number, float(total_amount),
                float(tax_amount), float(shipping_amount), 'pending',
                json.dumps(shipping_address), json.dumps(billing_address)
            )
        
        cursor.execute(order_query, order_params)
        order_row = cursor.fetchone()
        
        # Insert order items
        for item in items:
            item_id = str(uuid.uuid4())
            
            if tenant_context.tenant_tier == 'pool':
                item_query = """
                    INSERT INTO order_items (
                        order_item_id, tenant_id, order_id, product_id, 
                        quantity, unit_price
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                item_params = (
                    item_id, tenant_context.tenant_id, order_id,
                    item['product_id'], item['quantity'], item['unit_price']
                )
            else:
                item_query = """
                    INSERT INTO order_items (
                        order_item_id, order_id, product_id, quantity, unit_price
                    )
                    VALUES (%s, %s, %s, %s, %s)
                """
                item_params = (
                    item_id, order_id, item['product_id'],
                    item['quantity'], item['unit_price']
                )
            
            cursor.execute(item_query, item_params)
        
        connection.commit()
        
        return create_response(201, {
            'message': 'Order created',
            'order': {
                'order_id': str(order_row[0]),
                'order_number': order_row[1],
                'total_amount': float(order_row[2]),
                'created_at': order_row[3].isoformat()
            }
        })
        
    except Exception as e:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def update_order_status(order_id: str, event: Dict[str, Any], tenant_context: TenantContext) -> Dict[str, Any]:
    """Update order status"""
    body = json.loads(event.get('body', '{}'))
    
    if 'status' not in body:
        return create_response(400, {'error': 'Missing status field'})
    
    new_status = body['status']
    valid_statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
    
    if new_status not in valid_statuses:
        return create_response(400, {
            'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
        })
    
    query = "UPDATE orders SET status = %s, updated_at = NOW() WHERE order_id = %s"
    params = [new_status, order_id]
    
    if tenant_context.tenant_tier == 'pool':
        query += " AND tenant_id = %s"
        params.append(tenant_context.tenant_id)
    
    query += " RETURNING order_id, order_number, status, updated_at"
    
    connection = get_database_connection(tenant_context)
    cursor = connection.cursor()
    
    try:
        cursor.execute(query, tuple(params))
        connection.commit()
        
        row = cursor.fetchone()
        
        if not row:
            return create_response(404, {'error': 'Order not found'})
        
        return create_response(200, {
            'message': 'Order status updated',
            'order': {
                'order_id': str(row[0]),
                'order_number': row[1],
                'status': row[2],
                'updated_at': row[3].isoformat()
            }
        })
        
    finally:
        cursor.close()
        connection.close()


def get_database_connection(tenant_context: TenantContext):
    """Get database connection with proper tenant context"""
    import psycopg2
    import boto3
    from tenant_context import get_database_connection_params
    
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
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
        },
        'body': json.dumps(body, default=str)
    }
