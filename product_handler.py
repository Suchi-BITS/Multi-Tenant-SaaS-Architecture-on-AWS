"""
Product Service

Handles product catalog operations with tenant isolation:
- List products (with pagination)
- Get product details
- Create product
- Update product
- Delete product

Demonstrates data partitioning patterns for multi-tenancy.
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


class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert DynamoDB Decimal to JSON."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


@tenant_aware_handler
def list_products(event, context):
    """
    Lists all products for a tenant with pagination support.
    
    Query parameters:
    - limit: Number of items per page (default: 20)
    - last_key: Pagination token from previous response
    - category: Filter by category (optional)
    """
    try:
        tenant_context = event['tenant_context']
        query_params = event.get('queryStringParameters') or {}
        
        limit = int(query_params.get('limit', 20))
        last_key = query_params.get('last_key')
        category = query_params.get('category')
        
        # Get appropriate table name based on isolation model
        table_name = get_table_name(
            'products', 
            tenant_context.tenant_id, 
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        # Build query based on isolation model
        if ISOLATION_MODEL == 'pool':
            # Pool model: Query by tenant_id partition key
            query_kwargs = {
                'KeyConditionExpression': Key('tenant_id').eq(tenant_context.tenant_id),
                'Limit': limit
            }
            
            if category:
                query_kwargs['FilterExpression'] = Attr('category').eq(category)
            
            if last_key:
                query_kwargs['ExclusiveStartKey'] = json.loads(last_key)
            
            response = table.query(**query_kwargs)
            
        else:
            # Silo model: Scan tenant-specific table
            scan_kwargs = {
                'Limit': limit
            }
            
            if category:
                scan_kwargs['FilterExpression'] = Attr('category').eq(category)
            
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = json.loads(last_key)
            
            response = table.scan(**scan_kwargs)
        
        products = response.get('Items', [])
        
        result = {
            'products': products,
            'count': len(products)
        }
        
        # Add pagination token if more results exist
        if 'LastEvaluatedKey' in response:
            result['next_key'] = json.dumps(
                response['LastEvaluatedKey'], 
                cls=DecimalEncoder
            )
        
        return create_response(200, result, tenant_context)
        
    except Exception as e:
        print(f"Error listing products: {str(e)}")
        return create_response(500, {
            'error': 'Failed to list products',
            'details': str(e)
        })


@tenant_aware_handler
def get_product(event, context):
    """
    Retrieves a specific product by ID.
    Enforces tenant isolation.
    """
    try:
        tenant_context = event['tenant_context']
        path_params = event.get('pathParameters', {})
        product_id = path_params.get('id')
        
        if not product_id:
            return create_response(400, {
                'error': 'product_id is required'
            })
        
        table_name = get_table_name(
            'products',
            tenant_context.tenant_id,
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        # Get product
        if ISOLATION_MODEL == 'pool':
            response = table.get_item(
                Key={
                    'tenant_id': tenant_context.tenant_id,
                    'product_id': product_id
                }
            )
        else:
            response = table.get_item(
                Key={'product_id': product_id}
            )
        
        if 'Item' not in response:
            return create_response(404, {
                'error': 'Product not found'
            })
        
        product = response['Item']
        
        # Enforce tenant isolation for pool model
        if ISOLATION_MODEL == 'pool':
            enforce_tenant_isolation(
                tenant_context,
                product.get('tenant_id')
            )
        
        return create_response(200, product, tenant_context)
        
    except Exception as e:
        print(f"Error getting product: {str(e)}")
        return create_response(500, {
            'error': 'Failed to get product',
            'details': str(e)
        })


@tenant_aware_handler
def create_product(event, context):
    """
    Creates a new product.
    Checks tenant limits before creation.
    
    Request body:
    {
        "name": "Product Name",
        "description": "Product description",
        "price": 99.99,
        "category": "Electronics",
        "sku": "PROD-001",
        "inventory": 100
    }
    """
    try:
        tenant_context = event['tenant_context']
        body = json.loads(event['body'])
        
        # Validate required fields
        required_fields = ['name', 'price']
        for field in required_fields:
            if field not in body:
                return create_response(400, {
                    'error': f'{field} is required'
                })
        
        # Check tenant limits
        table_name = get_table_name(
            'products',
            tenant_context.tenant_id,
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        # Count existing products
        if ISOLATION_MODEL == 'pool':
            count_response = table.query(
                KeyConditionExpression=Key('tenant_id').eq(tenant_context.tenant_id),
                Select='COUNT'
            )
        else:
            count_response = table.scan(Select='COUNT')
        
        current_count = count_response.get('Count', 0)
        
        if not check_tenant_limits(tenant_context, 'products', current_count):
            return create_response(403, {
                'error': 'Product limit reached for your subscription tier',
                'current_count': current_count
            })
        
        # Generate product ID
        product_id = str(uuid.uuid4())
        
        # Create product record
        product = {
            'product_id': product_id,
            'name': body['name'],
            'description': body.get('description', ''),
            'price': Decimal(str(body['price'])),
            'category': body.get('category', 'Uncategorized'),
            'sku': body.get('sku', ''),
            'inventory': body.get('inventory', 0),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Add tenant_id for pool model
        if ISOLATION_MODEL == 'pool':
            product['tenant_id'] = tenant_context.tenant_id
        
        # Store in DynamoDB
        table.put_item(Item=product)
        
        return create_response(201, {
            'message': 'Product created successfully',
            'product': json.loads(json.dumps(product, cls=DecimalEncoder))
        }, tenant_context)
        
    except Exception as e:
        print(f"Error creating product: {str(e)}")
        return create_response(500, {
            'error': 'Failed to create product',
            'details': str(e)
        })


@tenant_aware_handler
def update_product(event, context):
    """
    Updates an existing product.
    Enforces tenant isolation.
    """
    try:
        tenant_context = event['tenant_context']
        path_params = event.get('pathParameters', {})
        product_id = path_params.get('id')
        
        if not product_id:
            return create_response(400, {
                'error': 'product_id is required'
            })
        
        body = json.loads(event['body'])
        
        table_name = get_table_name(
            'products',
            tenant_context.tenant_id,
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        # Verify product exists and belongs to tenant
        if ISOLATION_MODEL == 'pool':
            get_response = table.get_item(
                Key={
                    'tenant_id': tenant_context.tenant_id,
                    'product_id': product_id
                }
            )
        else:
            get_response = table.get_item(
                Key={'product_id': product_id}
            )
        
        if 'Item' not in get_response:
            return create_response(404, {
                'error': 'Product not found'
            })
        
        # Build update expression
        update_parts = []
        expression_values = {}
        
        updatable_fields = ['name', 'description', 'price', 'category', 'sku', 'inventory']
        
        for field in updatable_fields:
            if field in body:
                update_parts.append(f"{field} = :{field}")
                value = body[field]
                if field == 'price':
                    value = Decimal(str(value))
                expression_values[f":{field}"] = value
        
        if not update_parts:
            return create_response(400, {
                'error': 'No valid fields to update'
            })
        
        update_parts.append("updated_at = :updated_at")
        expression_values[':updated_at'] = datetime.utcnow().isoformat()
        
        update_expression = "SET " + ", ".join(update_parts)
        
        # Update in DynamoDB
        if ISOLATION_MODEL == 'pool':
            key = {
                'tenant_id': tenant_context.tenant_id,
                'product_id': product_id
            }
        else:
            key = {'product_id': product_id}
        
        response = table.update_item(
            Key=key,
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ReturnValues='ALL_NEW'
        )
        
        return create_response(200, {
            'message': 'Product updated successfully',
            'product': json.loads(json.dumps(response['Attributes'], cls=DecimalEncoder))
        }, tenant_context)
        
    except Exception as e:
        print(f"Error updating product: {str(e)}")
        return create_response(500, {
            'error': 'Failed to update product',
            'details': str(e)
        })


@tenant_aware_handler
def delete_product(event, context):
    """
    Deletes a product.
    Enforces tenant isolation.
    """
    try:
        tenant_context = event['tenant_context']
        path_params = event.get('pathParameters', {})
        product_id = path_params.get('id')
        
        if not product_id:
            return create_response(400, {
                'error': 'product_id is required'
            })
        
        table_name = get_table_name(
            'products',
            tenant_context.tenant_id,
            ISOLATION_MODEL
        )
        table = DynamoDBConnection.get_table(table_name)
        
        # Verify product exists and belongs to tenant
        if ISOLATION_MODEL == 'pool':
            get_response = table.get_item(
                Key={
                    'tenant_id': tenant_context.tenant_id,
                    'product_id': product_id
                }
            )
            key = {
                'tenant_id': tenant_context.tenant_id,
                'product_id': product_id
            }
        else:
            get_response = table.get_item(
                Key={'product_id': product_id}
            )
            key = {'product_id': product_id}
        
        if 'Item' not in get_response:
            return create_response(404, {
                'error': 'Product not found'
            })
        
        # Delete from DynamoDB
        table.delete_item(Key=key)
        
        return create_response(200, {
            'message': 'Product deleted successfully',
            'product_id': product_id
        }, tenant_context)
        
    except Exception as e:
        print(f"Error deleting product: {str(e)}")
        return create_response(500, {
            'error': 'Failed to delete product',
            'details': str(e)
        })
