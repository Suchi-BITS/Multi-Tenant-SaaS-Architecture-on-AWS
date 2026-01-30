"""
Tenant Onboarding Lambda Function
Handles the onboarding of new tenants in the multi-tenant SaaS application
"""

import json
import os
import boto3
import uuid
from datetime import datetime
from typing import Dict, Any

# AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')
rds_data = boto3.client('rds-data')
cognito = boto3.client('cognito-idp')

# Environment variables
TENANTS_TABLE = os.environ.get('TENANTS_TABLE')
USER_POOL_ID = os.environ.get('USER_POOL_ID')
TENANT_TIER = os.environ.get('TENANT_TIER', 'pool')

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for tenant onboarding
    
    Args:
        event: Lambda event containing tenant details
        context: Lambda context
        
    Returns:
        Response with tenant information
    """
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # Validate required fields
        required_fields = ['company_name', 'admin_email', 'tier']
        missing_fields = [field for field in required_fields if field not in body]
        
        if missing_fields:
            return create_response(400, {
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            })
        
        # Generate tenant ID
        tenant_id = str(uuid.uuid4())
        
        # Create tenant record
        tenant_data = {
            'tenant_id': tenant_id,
            'company_name': body['company_name'],
            'admin_email': body['admin_email'],
            'tier': body['tier'],
            'status': 'provisioning',
            'created_at': datetime.utcnow().isoformat(),
            'settings': body.get('settings', {})
        }
        
        # Store tenant metadata in DynamoDB
        save_tenant_metadata(tenant_data)
        
        # Provision resources based on tier
        if body['tier'] == 'pool':
            provision_pool_tenant(tenant_id)
        elif body['tier'] == 'bridge':
            provision_bridge_tenant(tenant_id)
        elif body['tier'] == 'silo':
            provision_silo_tenant(tenant_id)
        else:
            raise ValueError(f"Invalid tier: {body['tier']}")
        
        # Create admin user in Cognito
        admin_user = create_admin_user(tenant_id, body['admin_email'])
        
        # Update tenant status
        update_tenant_status(tenant_id, 'active')
        
        return create_response(201, {
            'message': 'Tenant onboarded successfully',
            'tenant_id': tenant_id,
            'admin_user': admin_user
        })
        
    except Exception as e:
        print(f"Error onboarding tenant: {str(e)}")
        return create_response(500, {
            'error': 'Failed to onboard tenant',
            'details': str(e)
        })


def save_tenant_metadata(tenant_data: Dict[str, Any]) -> None:
    """Save tenant metadata to DynamoDB"""
    table = dynamodb.Table(TENANTS_TABLE)
    table.put_item(Item=tenant_data)
    print(f"Saved tenant metadata for {tenant_data['tenant_id']}")


def provision_pool_tenant(tenant_id: str) -> None:
    """
    Provision resources for pool model tenant
    - Adds tenant row to shared database
    - Sets up row-level security
    """
    print(f"Provisioning pool tenant: {tenant_id}")
    
    # In pool model, we just need to ensure the tenant_id is ready for use
    # The shared database and tables already exist
    
    # Initialize tenant in shared database
    db_secret = get_database_credentials()
    
    # Create tenant-specific schema or prepare row-level security
    sql = f"""
    -- Insert tenant record
    INSERT INTO tenants (tenant_id, created_at)
    VALUES ('{tenant_id}', NOW())
    ON CONFLICT (tenant_id) DO NOTHING;
    """
    
    execute_sql(db_secret, sql)
    print(f"Pool tenant {tenant_id} provisioned")


def provision_bridge_tenant(tenant_id: str) -> None:
    """
    Provision resources for bridge model tenant
    - Creates dedicated database schema
    - Sets up schema-level isolation
    """
    print(f"Provisioning bridge tenant: {tenant_id}")
    
    db_secret = get_database_credentials()
    
    # Create dedicated schema for tenant
    sql = f"""
    -- Create tenant schema
    CREATE SCHEMA IF NOT EXISTS tenant_{tenant_id.replace('-', '_')};
    
    -- Create tables in tenant schema
    CREATE TABLE IF NOT EXISTS tenant_{tenant_id.replace('-', '_')}.users (
        user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(255) UNIQUE NOT NULL,
        name VARCHAR(255),
        created_at TIMESTAMP DEFAULT NOW()
    );
    
    CREATE TABLE IF NOT EXISTS tenant_{tenant_id.replace('-', '_')}.products (
        product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(255) NOT NULL,
        description TEXT,
        price DECIMAL(10, 2),
        created_at TIMESTAMP DEFAULT NOW()
    );
    
    CREATE TABLE IF NOT EXISTS tenant_{tenant_id.replace('-', '_')}.orders (
        order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES tenant_{tenant_id.replace('-', '_')}.users(user_id),
        total_amount DECIMAL(10, 2),
        status VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    execute_sql(db_secret, sql)
    print(f"Bridge tenant {tenant_id} provisioned with dedicated schema")


def provision_silo_tenant(tenant_id: str) -> None:
    """
    Provision resources for silo model tenant
    - Triggers infrastructure provisioning (via Step Functions or CodePipeline)
    - Creates dedicated RDS instance, VPC resources, etc.
    """
    print(f"Provisioning silo tenant: {tenant_id}")
    
    # In a real implementation, this would trigger:
    # 1. Terraform/CloudFormation stack creation
    # 2. Dedicated VPC, RDS, Lambda, etc.
    # 3. Update tenant metadata with resource ARNs
    
    # For this example, we'll simulate the process
    step_functions = boto3.client('stepfunctions')
    
    # Trigger Step Functions state machine for infrastructure provisioning
    # state_machine_arn = os.environ.get('SILO_PROVISIONING_STATE_MACHINE')
    # step_functions.start_execution(
    #     stateMachineArn=state_machine_arn,
    #     input=json.dumps({'tenant_id': tenant_id})
    # )
    
    print(f"Silo tenant {tenant_id} provisioning initiated")


def create_admin_user(tenant_id: str, email: str) -> Dict[str, Any]:
    """Create admin user in Cognito"""
    try:
        response = cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'custom:tenant_id', 'Value': tenant_id}
            ],
            DesiredDeliveryMediums=['EMAIL']
        )
        
        print(f"Created admin user {email} for tenant {tenant_id}")
        return {
            'username': email,
            'user_sub': response['User']['Username']
        }
    except cognito.exceptions.UsernameExistsException:
        print(f"User {email} already exists")
        return {'username': email, 'exists': True}


def update_tenant_status(tenant_id: str, status: str) -> None:
    """Update tenant status in DynamoDB"""
    table = dynamodb.Table(TENANTS_TABLE)
    table.update_item(
        Key={'tenant_id': tenant_id},
        UpdateExpression='SET #status = :status, updated_at = :updated_at',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={
            ':status': status,
            ':updated_at': datetime.utcnow().isoformat()
        }
    )
    print(f"Updated tenant {tenant_id} status to {status}")


def get_database_credentials() -> Dict[str, Any]:
    """Retrieve database credentials from Secrets Manager"""
    secret_name = os.environ.get('DB_SECRET_NAME')
    response = secrets_manager.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])


def execute_sql(db_secret: Dict[str, Any], sql: str) -> None:
    """Execute SQL using RDS Data API"""
    db_cluster_arn = os.environ.get('DB_CLUSTER_ARN')
    db_secret_arn = os.environ.get('DB_SECRET_ARN')
    database = db_secret.get('dbname')
    
    try:
        rds_data.execute_statement(
            resourceArn=db_cluster_arn,
            secretArn=db_secret_arn,
            database=database,
            sql=sql
        )
        print("SQL executed successfully")
    except Exception as e:
        print(f"Error executing SQL: {str(e)}")
        raise


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
        'body': json.dumps(body)
    }
