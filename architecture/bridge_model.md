# Bridge Model Architecture Implementation

## Overview
The Bridge Model provides a balanced approach with shared compute resources but isolated database schemas per tenant, offering better data separation while maintaining cost efficiency.

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│              Client Applications             │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│           API Gateway (Shared)               │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│        Lambda Functions (Shared)             │
│         with Schema Routing Logic            │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│      Single RDS Cluster (Shared)             │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │  Schema: tenant_abc                │     │
│  │  - users                           │     │
│  │  - products                        │     │
│  │  - orders                          │     │
│  └────────────────────────────────────┘     │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │  Schema: tenant_xyz                │     │
│  │  - users                           │     │
│  │  - products                        │     │
│  │  - orders                          │     │
│  └────────────────────────────────────┘     │
└─────────────────────────────────────────────┘
```

## Database Schema Template

```sql
-- Schema creation template for each tenant
DO $$
DECLARE
    schema_name TEXT := 'tenant_<TENANT_ID>';
BEGIN
    -- Create schema
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', schema_name);
    
    -- Set search path
    EXECUTE format('SET search_path TO %I', schema_name);
    
    -- Create tables
    EXECUTE format('
        CREATE TABLE %I.users (
            user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255),
            role VARCHAR(50) DEFAULT ''user'',
            status VARCHAR(50) DEFAULT ''active'',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )', schema_name);
    
    EXECUTE format('
        CREATE TABLE %I.products (
            product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            price DECIMAL(10, 2) NOT NULL,
            stock_quantity INTEGER DEFAULT 0,
            sku VARCHAR(100) UNIQUE,
            category VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )', schema_name);
    
    EXECUTE format('
        CREATE TABLE %I.orders (
            order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES %I.users(user_id),
            total_amount DECIMAL(10, 2) NOT NULL,
            tax_amount DECIMAL(10, 2) DEFAULT 0,
            shipping_amount DECIMAL(10, 2) DEFAULT 0,
            status VARCHAR(50) DEFAULT ''pending'',
            shipping_address TEXT,
            billing_address TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )', schema_name, schema_name);
    
    EXECUTE format('
        CREATE TABLE %I.order_items (
            order_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES %I.orders(order_id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES %I.products(product_id),
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            unit_price DECIMAL(10, 2) NOT NULL,
            subtotal DECIMAL(10, 2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
            created_at TIMESTAMP DEFAULT NOW()
        )', schema_name, schema_name, schema_name);
    
    -- Create indexes
    EXECUTE format('CREATE INDEX idx_%I_users_email ON %I.users(email)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX idx_%I_products_category ON %I.products(category)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX idx_%I_orders_user ON %I.orders(user_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX idx_%I_orders_status ON %I.orders(status)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX idx_%I_order_items_order ON %I.order_items(order_id)', schema_name, schema_name);
    
    -- Create audit trigger
    EXECUTE format('
        CREATE OR REPLACE FUNCTION %I.update_updated_at()
        RETURNS TRIGGER AS $func$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql', schema_name);
    
    EXECUTE format('
        CREATE TRIGGER update_users_updated_at
        BEFORE UPDATE ON %I.users
        FOR EACH ROW EXECUTE FUNCTION %I.update_updated_at()', schema_name, schema_name);
    
    EXECUTE format('
        CREATE TRIGGER update_products_updated_at
        BEFORE UPDATE ON %I.products
        FOR EACH ROW EXECUTE FUNCTION %I.update_updated_at()', schema_name, schema_name);
    
    EXECUTE format('
        CREATE TRIGGER update_orders_updated_at
        BEFORE UPDATE ON %I.orders
        FOR EACH ROW EXECUTE FUNCTION %I.update_updated_at()', schema_name, schema_name);
    
END $$;
```

## Connection Routing

```python
# Python connection routing logic
def get_database_connection(tenant_id: str):
    """Get database connection with correct schema"""
    schema_name = f"tenant_{tenant_id.replace('-', '_')}"
    
    connection = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    
    # Set search path to tenant schema
    cursor = connection.cursor()
    cursor.execute(f"SET search_path TO {schema_name}")
    cursor.close()
    
    return connection

# Usage in Lambda
def lambda_handler(event, context, tenant_context):
    conn = get_database_connection(tenant_context.tenant_id)
    
    # All queries now automatically use the tenant schema
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    users = cursor.fetchall()
```

## Configuration

### Terraform Variables
```hcl
bridge_config = {
  instance_class = "db.t3.small"
  allocated_storage = 50
  max_connections = 200
  lambda_memory = 1024
  lambda_timeout = 60
  max_tenants = 500
  backup_retention = 7
}
```

### Schema Management

```python
# Schema provisioning script
import psycopg2
import os

def provision_tenant_schema(tenant_id: str):
    """Provision new tenant schema"""
    schema_name = f"tenant_{tenant_id.replace('-', '_')}"
    
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )
    
    cursor = conn.cursor()
    
    try:
        # Read schema template
        with open('schema_template.sql', 'r') as f:
            template = f.read()
        
        # Replace placeholders
        schema_sql = template.replace('<TENANT_ID>', tenant_id.replace('-', '_'))
        
        # Execute
        cursor.execute(schema_sql)
        conn.commit()
        
        print(f"Schema {schema_name} provisioned successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"Error provisioning schema: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def drop_tenant_schema(tenant_id: str):
    """Drop tenant schema (use with caution)"""
    schema_name = f"tenant_{tenant_id.replace('-', '_')}"
    
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )
    
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"DROP SCHEMA {schema_name} CASCADE")
        conn.commit()
        print(f"Schema {schema_name} dropped successfully")
    except Exception as e:
        conn.rollback()
        print(f"Error dropping schema: {e}")
        raise
    finally:
        cursor.close()
        conn.close()
```

### Cost Estimate (Per Tenant)
- RDS Instance Share: $50-100/month
- Lambda: $10-20/month
- API Gateway: $3.50/million requests
- S3: $2-5/month
- **Total per tenant: $150-300/month**

## Advantages
✅ Better data isolation than Pool
✅ Moderate cost increase
✅ Easier compliance auditing
✅ Per-tenant backup/restore possible
✅ Better performance isolation

## Disadvantages
❌ More complex schema management
❌ Higher operational overhead
❌ Database size grows with tenants
❌ Migration complexity increases
❌ Limited to ~500 tenants per instance

## Best Use Cases
- Mid-market businesses
- Regulated industries (finance, healthcare)
- SaaS with data residency requirements
- Applications requiring per-tenant backups
- Growing customer base

## Monitoring

Key metrics:
- Schema count and sizes
- Connection pool usage per schema
- Query performance per schema
- Storage usage per schema
- Backup duration per schema

## Security Considerations

1. **Schema-level permissions** for each tenant
2. **Prevent cross-schema access** in application code
3. **Regular schema audits** for data leakage
4. **Encrypted connections** always
5. **Schema-level backup encryption**

## Migration Paths

### From Pool to Bridge:
```sql
-- 1. Create new schema
CREATE SCHEMA tenant_abc;

-- 2. Copy data
INSERT INTO tenant_abc.users 
SELECT user_id, email, name, role, created_at, updated_at
FROM public.users 
WHERE tenant_id = 'abc';

-- 3. Verify data
SELECT COUNT(*) FROM tenant_abc.users;
SELECT COUNT(*) FROM public.users WHERE tenant_id = 'abc';

-- 4. Switch application traffic
-- 5. Archive old data
DELETE FROM public.users WHERE tenant_id = 'abc';
```

### To Silo:
1. Export schema to SQL dump
2. Create dedicated RDS instance
3. Import schema
4. Update connection strings
5. Switch traffic
6. Decommission old schema

## Performance Optimization

```sql
-- Analyze table statistics
ANALYZE tenant_abc.users;
ANALYZE tenant_abc.products;
ANALYZE tenant_abc.orders;

-- Vacuum to reclaim space
VACUUM ANALYZE tenant_abc.users;

-- Create materialized views for reports
CREATE MATERIALIZED VIEW tenant_abc.sales_summary AS
SELECT 
    DATE_TRUNC('day', created_at) as date,
    COUNT(*) as order_count,
    SUM(total_amount) as total_sales
FROM tenant_abc.orders
GROUP BY DATE_TRUNC('day', created_at);

-- Refresh periodically
REFRESH MATERIALIZED VIEW tenant_abc.sales_summary;
```
