"""
Order Service

Handles order processing with tenant isolation:
- List orders (with filtering and pagination)
- Get order details
- Create order
- Update order status
- Cancel order

Demonstrates transaction patterns and status workflows in multi-tenant SaaS.
"""

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

import boto3
from boto3.dynamodb.conditions import Key, Attr

# Import shared utilities
import sys
sys.path.append('/opt/python')
from tenant_utils import (
    tenant_aware_handler,
    create_response,
    get_table_name,
    enforce_tenant_isolation,
    check_tenant_limits,
    DynamoDBConnection
)

# Environment variables
ISOLATION_MODEL = os.environ.get('ISOLATION_MODEL', 'pool')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')

# AWS clients
sns_client = boto3.client('sns')


class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert DynamoDB Decimal to JSON."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


@tenant_aware_handler
def list_orders(event, context):
    """
    Lists all orders for a tenant with filtering and pagination.
    
    Query parameters:
    - limit: Number of items per page (default: 20)
    - last_key: Pagination token
    - status: Filter by status (pending, confirmed, shipped, delivered, cancelled)
    - from_date: Filter orders after this date (ISO format)
    - to_date: Filter orders before this date (ISO format)
    """
    try:
        tenant_context = event['tenant_context']
        query_params = event.get('queryStringParameters') or {}
        
        limit = int(query_params.get('limit', 20))
        last_key = query_params.get('last_key')
        status_filter = query_params.get('status')
        from_date = query_params.get('from_date')
        to_date = query_params.get('to_date')
        
        table_name = get_table_name(
            'orders',
            tenant_context.tenant_id,
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        # Build query
        if ISOLATION_MODEL == 'pool':
            query_kwargs = {
                'KeyConditionExpression': Key('tenant_id').eq(tenant_context.tenant_id),
                'Limit': limit
            }
            
            # Add filters
            filter_expressions = []
            if status_filter:
                filter_expressions.append(Attr('status').eq(status_filter))
            if from_date:
                filter_expressions.append(Attr('created_at').gte(from_date))
            if to_date:
                filter_expressions.append(Attr('created_at').lte(to_date))
            
            if filter_expressions:
                combined_filter = filter_expressions[0]
                for expr in filter_expressions[1:]:
                    combined_filter = combined_filter & expr
                query_kwargs['FilterExpression'] = combined_filter
            
            if last_key:
                query_kwargs['ExclusiveStartKey'] = json.loads(last_key)
            
            response = table.query(**query_kwargs)
            
        else:
            # Silo model: Scan tenant-specific table
            scan_kwargs = {'Limit': limit}
            
            filter_expressions = []
            if status_filter:
                filter_expressions.append(Attr('status').eq(status_filter))
            if from_date:
                filter_expressions.append(Attr('created_at').gte(from_date))
            if to_date:
                filter_expressions.append(Attr('created_at').lte(to_date))
            
            if filter_expressions:
                combined_filter = filter_expressions[0]
                for expr in filter_expressions[1:]:
                    combined_filter = combined_filter & expr
                scan_kwargs['FilterExpression'] = combined_filter
            
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = json.loads(last_key)
            
            response = table.scan(**scan_kwargs)
        
        orders = response.get('Items', [])
        
        result = {
            'orders': json.loads(json.dumps(orders, cls=DecimalEncoder)),
            'count': len(orders)
        }
        
        if 'LastEvaluatedKey' in response:
            result['next_key'] = json.dumps(
                response['LastEvaluatedKey'],
                cls=DecimalEncoder
            )
        
        return create_response(200, result, tenant_context)
        
    except Exception as e:
        print(f"Error listing orders: {str(e)}")
        return create_response(500, {
            'error': 'Failed to list orders',
            'details': str(e)
        })


@tenant_aware_handler
def get_order(event, context):
    """
    Retrieves a specific order by ID.
    Enforces tenant isolation.
    """
    try:
        tenant_context = event['tenant_context']
        path_params = event.get('pathParameters', {})
        order_id = path_params.get('id')
        
        if not order_id:
            return create_response(400, {
                'error': 'order_id is required'
            })
        
        table_name = get_table_name(
            'orders',
            tenant_context.tenant_id,
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        if ISOLATION_MODEL == 'pool':
            response = table.get_item(
                Key={
                    'tenant_id': tenant_context.tenant_id,
                    'order_id': order_id
                }
            )
        else:
            response = table.get_item(
                Key={'order_id': order_id}
            )
        
        if 'Item' not in response:
            return create_response(404, {
                'error': 'Order not found'
            })
        
        order = response['Item']
        
        # Enforce tenant isolation
        if ISOLATION_MODEL == 'pool':
            enforce_tenant_isolation(
                tenant_context,
                order.get('tenant_id')
            )
        
        return create_response(200, 
            json.loads(json.dumps(order, cls=DecimalEncoder)),
            tenant_context
        )
        
    except Exception as e:
        print(f"Error getting order: {str(e)}")
        return create_response(500, {
            'error': 'Failed to get order',
            'details': str(e)
        })


@tenant_aware_handler
def create_order(event, context):
    """
    Creates a new order.
    
    Request body:
    {
        "customer_email": "customer@example.com",
        "items": [
            {
                "product_id": "uuid",
                "product_name": "Product Name",
                "quantity": 2,
                "price": 99.99
            }
        ],
        "shipping_address": {
            "street": "123 Main St",
            "city": "Seattle",
            "state": "WA",
            "zip": "98101"
        }
    }
    """
    try:
        tenant_context = event['tenant_context']
        body = json.loads(event['body'])
        
        # Validate required fields
        if 'customer_email' not in body or 'items' not in body:
            return create_response(400, {
                'error': 'customer_email and items are required'
            })
        
        if not body['items']:
            return create_response(400, {
                'error': 'Order must contain at least one item'
            })
        
        # Check tenant limits
        table_name = get_table_name(
            'orders',
            tenant_context.tenant_id,
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        if ISOLATION_MODEL == 'pool':
            count_response = table.query(
                KeyConditionExpression=Key('tenant_id').eq(tenant_context.tenant_id),
                Select='COUNT'
            )
        else:
            count_response = table.scan(Select='COUNT')
        
        current_count = count_response.get('Count', 0)
        
        if not check_tenant_limits(tenant_context, 'orders', current_count):
            return create_response(403, {
                'error': 'Order limit reached for your subscription tier',
                'current_count': current_count
            })
        
        # Generate order ID
        order_id = str(uuid.uuid4())
        
        # Calculate total
        total_amount = Decimal('0')
        processed_items = []
        
        for item in body['items']:
            quantity = item.get('quantity', 1)
            price = Decimal(str(item.get('price', 0)))
            item_total = price * quantity
            total_amount += item_total
            
            processed_items.append({
                'product_id': item.get('product_id'),
                'product_name': item.get('product_name'),
                'quantity': quantity,
                'price': price,
                'subtotal': item_total
            })
        
        # Create order record
        order = {
            'order_id': order_id,
            'customer_email': body['customer_email'],
            'items': processed_items,
            'total_amount': total_amount,
            'status': 'pending',
            'shipping_address': body.get('shipping_address', {}),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Add tenant_id for pool model
        if ISOLATION_MODEL == 'pool':
            order['tenant_id'] = tenant_context.tenant_id
        
        # Store in DynamoDB
        table.put_item(Item=order)
        
        # Publish order created event
        publish_order_event(tenant_context, order_id, 'ORDER_CREATED')
        
        return create_response(201, {
            'message': 'Order created successfully',
            'order': json.loads(json.dumps(order, cls=DecimalEncoder))
        }, tenant_context)
        
    except Exception as e:
        print(f"Error creating order: {str(e)}")
        return create_response(500, {
            'error': 'Failed to create order',
            'details': str(e)
        })


@tenant_aware_handler
def update_order(event, context):
    """
    Updates order status.
    
    Valid status transitions:
    - pending -> confirmed
    - confirmed -> shipped
    - shipped -> delivered
    - Any status -> cancelled
    """
    try:
        tenant_context = event['tenant_context']
        path_params = event.get('pathParameters', {})
        order_id = path_params.get('id')
        
        if not order_id:
            return create_response(400, {
                'error': 'order_id is required'
            })
        
        body = json.loads(event['body'])
        new_status = body.get('status')
        
        if not new_status:
            return create_response(400, {
                'error': 'status is required'
            })
        
        valid_statuses = ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled']
        if new_status not in valid_statuses:
            return create_response(400, {
                'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            })
        
        table_name = get_table_name(
            'orders',
            tenant_context.tenant_id,
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        # Get current order
        if ISOLATION_MODEL == 'pool':
            get_response = table.get_item(
                Key={
                    'tenant_id': tenant_context.tenant_id,
                    'order_id': order_id
                }
            )
            key = {
                'tenant_id': tenant_context.tenant_id,
                'order_id': order_id
            }
        else:
            get_response = table.get_item(
                Key={'order_id': order_id}
            )
            key = {'order_id': order_id}
        
        if 'Item' not in get_response:
            return create_response(404, {
                'error': 'Order not found'
            })
        
        current_order = get_response['Item']
        current_status = current_order.get('status')
        
        # Validate status transition
        if not is_valid_status_transition(current_status, new_status):
            return create_response(400, {
                'error': f'Cannot transition from {current_status} to {new_status}'
            })
        
        # Update order
        response = table.update_item(
            Key=key,
            UpdateExpression='SET #status = :status, updated_at = :updated_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': new_status,
                ':updated_at': datetime.utcnow().isoformat()
            },
            ReturnValues='ALL_NEW'
        )
        
        # Publish status change event
        publish_order_event(tenant_context, order_id, f'ORDER_{new_status.upper()}')
        
        return create_response(200, {
            'message': 'Order updated successfully',
            'order': json.loads(json.dumps(response['Attributes'], cls=DecimalEncoder))
        }, tenant_context)
        
    except Exception as e:
        print(f"Error updating order: {str(e)}")
        return create_response(500, {
            'error': 'Failed to update order',
            'details': str(e)
        })


def is_valid_status_transition(current: str, new: str) -> bool:
    """
    Validates order status transitions.
    """
    valid_transitions = {
        'pending': ['confirmed', 'cancelled'],
        'confirmed': ['shipped', 'cancelled'],
        'shipped': ['delivered', 'cancelled'],
        'delivered': [],
        'cancelled': []
    }
    
    return new in valid_transitions.get(current, [])


def publish_order_event(tenant_context, order_id: str, event_type: str):
    """
    Publishes order events to SNS for event-driven workflows.
    
    This enables:
    - Sending confirmation emails
    - Triggering inventory updates
    - Notifying fulfillment systems
    - Updating analytics
    """
    try:
        if not SNS_TOPIC_ARN:
            return
        
        message = {
            'tenant_id': tenant_context.tenant_id,
            'order_id': order_id,
            'event_type': event_type,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps(message),
            Subject=f'Order Event: {event_type}',
            MessageAttributes={
                'tenant_id': {
                    'DataType': 'String',
                    'StringValue': tenant_context.tenant_id
                },
                'event_type': {
                    'DataType': 'String',
                    'StringValue': event_type
                }
            }
        )
        
        print(f"Published event: {event_type} for order: {order_id}")
        
    except Exception as e:
        print(f"Error publishing order event: {str(e)}")
