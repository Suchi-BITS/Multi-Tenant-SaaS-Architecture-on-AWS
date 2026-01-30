# Multi-Tenant SaaS Architecture Documentation

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Deployment Models](#deployment-models)
3. [Component Details](#component-details)
4. [Data Flow](#data-flow)
5. [Security Architecture](#security-architecture)
6. [Scaling Strategy](#scaling-strategy)

---

## Architecture Overview

The multi-tenant SaaS architecture is built on AWS serverless and managed services, providing a scalable, secure, and cost-effective solution for serving multiple customers.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
│   Web App │ Mobile App │ Third-party Integrations           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     CloudFront (CDN)                         │
│              SSL/TLS │ DDoS Protection │ Caching            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   API Gateway (Regional)                     │
│    Request Validation │ Authorization │ Throttling          │
│         Rate Limiting │ Request/Response Transform          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Cognito Authorizer                        │
│         JWT Validation │ Tenant Context Extraction           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Lambda Functions                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Tenant     │  │    User      │  │   Product    │      │
│  │  Onboarding  │  │  Management  │  │   Service    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Lambda Layers (Shared Libraries)             │  │
│  │  Tenant Context │ Logging │ Metrics │ Data Access   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
    ┌──────────────────────┐   ┌──────────────────────┐
    │   Amazon RDS         │   │   DynamoDB           │
    │   (PostgreSQL)       │   │   (Metadata)         │
    │                      │   │                      │
    │  • Tenant Data       │   │  • Tenant Registry   │
    │  • Transactional     │   │  • User Sessions     │
    │  • Multi-tier        │   │  • Configuration     │
    └──────────────────────┘   └──────────────────────┘
                  │
                  ▼
    ┌──────────────────────────────────────┐
    │        Amazon S3                      │
    │   Tenant-scoped Storage               │
    │   /tenants/{tenant-id}/...            │
    └──────────────────────────────────────┘
```

---

## Deployment Models

### 1. Pool Model (Shared Everything)

**Architecture:**
```
┌────────────────────────────────────────────────────────┐
│                  API Gateway                           │
└────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Lambda A   │ │  Lambda B   │ │  Lambda C   │
│  (Shared)   │ │  (Shared)   │ │  (Shared)   │
└─────────────┘ └─────────────┘ └─────────────┘
        │               │               │
        └───────────────┼───────────────┘
                        ▼
            ┌──────────────────────┐
            │   Single RDS         │
            │                      │
            │  ┌────────────────┐  │
            │  │ Orders Table   │  │
            │  │ tenant_id PK   │  │
            │  └────────────────┘  │
            │                      │
            │  Row-Level Security  │
            └──────────────────────┘

Data Isolation Strategy:
- Row-Level Security (RLS) in PostgreSQL
- Every table has tenant_id column
- Application enforces tenant filter
- Shared compute and storage
```

**Cost Breakdown:**
- API Gateway: $3.50/million requests
- Lambda: $0.20/million requests
- RDS: ~$30-50/month (db.t3.micro)
- S3: ~$5/month
- **Total per tenant: $50-100/month**

### 2. Bridge Model (Isolated Schemas)

**Architecture:**
```
┌────────────────────────────────────────────────────────┐
│                  API Gateway                           │
└────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Lambda A   │ │  Lambda B   │ │  Lambda C   │
│  (Shared)   │ │  (Shared)   │ │  (Shared)   │
└─────────────┘ └─────────────┘ └─────────────┘
        │               │               │
        └───────────────┼───────────────┘
                        ▼
        ┌──────────────────────────────┐
        │      Shared RDS Cluster      │
        │                              │
        │  ┌──────────────────────┐    │
        │  │  Schema: tenant_a    │    │
        │  │  - users             │    │
        │  │  - products          │    │
        │  │  - orders            │    │
        │  └──────────────────────┘    │
        │                              │
        │  ┌──────────────────────┐    │
        │  │  Schema: tenant_b    │    │
        │  │  - users             │    │
        │  │  - products          │    │
        │  │  - orders            │    │
        │  └──────────────────────┘    │
        └──────────────────────────────┘

Data Isolation Strategy:
- Dedicated schema per tenant
- Connection routing based on tenant
- Compute shared, storage isolated
- Better data governance
```

**Cost Breakdown:**
- API Gateway: $3.50/million requests
- Lambda: $0.20/million requests
- RDS: ~$100-200/month (db.t3.small-medium)
- S3: ~$10/month
- **Total per tenant: $150-300/month**

### 3. Silo Model (Complete Isolation)

**Architecture:**
```
┌──────────────────────────────────────────────────────────┐
│              Tenant A Stack                              │
│                                                          │
│  ┌────────────────┐                                      │
│  │  API Gateway   │                                      │
│  │   (Tenant A)   │                                      │
│  └────────────────┘                                      │
│          │                                               │
│    ┌─────┴─────┐                                         │
│    ▼           ▼                                         │
│  ┌───────┐  ┌───────┐                                    │
│  │Lambda │  │Lambda │                                    │
│  │   A   │  │   B   │                                    │
│  └───────┘  └───────┘                                    │
│          │                                               │
│          ▼                                               │
│  ┌──────────────────┐     ┌──────────────────┐          │
│  │   RDS Instance   │     │   S3 Bucket      │          │
│  │   (Dedicated)    │     │   (Dedicated)    │          │
│  └──────────────────┘     └──────────────────┘          │
│                                                          │
│  ┌────────────────────────────────────────────┐         │
│  │         Dedicated VPC                       │         │
│  │  Private Subnets │ Security Groups         │         │
│  └────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│              Tenant B Stack                              │
│              (Identical architecture)                     │
└──────────────────────────────────────────────────────────┘

Data Isolation Strategy:
- Complete infrastructure isolation
- Dedicated VPC per tenant
- Dedicated database per tenant
- Maximum security and customization
- Geographic flexibility
```

**Cost Breakdown:**
- API Gateway: $3.50/million requests
- Lambda: $0.50/million requests
- RDS: ~$300-1000/month (dedicated)
- VPC: ~$30/month
- S3: ~$20/month
- **Total per tenant: $500-2000/month**

---

## Component Details

### API Gateway Configuration

```yaml
API Gateway:
  Type: Regional
  
  Stages:
    - dev
    - staging
    - prod
  
  Features:
    - Cognito Authorizer
    - Request Validation
    - Request/Response Transformation
    - CORS Configuration
    - API Keys (optional)
    - Usage Plans per Tenant
    
  Throttling:
    Pool: 1000 req/sec per tenant
    Bridge: 2000 req/sec per tenant
    Silo: Custom per tenant
    
  Caching:
    Enabled: true
    TTL: 300 seconds
    Capacity: 0.5 GB
```

### Lambda Function Architecture

```python
# Function Structure
lambda-function/
├── handler.py              # Main handler
├── requirements.txt        # Dependencies
├── models/                 # Data models
│   ├── __init__.py
│   └── tenant.py
├── services/              # Business logic
│   ├── __init__.py
│   ├── tenant_service.py
│   └── database_service.py
└── utils/                 # Utilities
    ├── __init__.py
    ├── logger.py
    └── metrics.py

# Configuration
Memory: 512-2048 MB (tier-based)
Timeout: 30-60 seconds
Runtime: Python 3.11
Architecture: arm64 (Graviton2)
Reserved Concurrency: 100-1000 (tier-based)

# Environment Variables
TENANT_TABLE: tenants
DB_SECRET_ARN: arn:aws:secretsmanager:...
S3_BUCKET: multitenant-data
LOG_LEVEL: INFO
TENANT_TIER: pool|bridge|silo
```

### Database Schema

#### Pool Model Schema

```sql
-- Tenants table
CREATE TABLE tenants (
    tenant_id UUID PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    tier VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Users table (shared, with tenant_id)
CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, email)
);

-- Row-Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON users
    USING (tenant_id = current_setting('app.current_tenant')::uuid);

-- Products table
CREATE TABLE products (
    product_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE products ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON products
    USING (tenant_id = current_setting('app.current_tenant')::uuid);

-- Orders table
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    user_id UUID NOT NULL REFERENCES users(user_id),
    total_amount DECIMAL(10, 2),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON orders
    USING (tenant_id = current_setting('app.current_tenant')::uuid);

-- Indexes for performance
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_products_tenant ON products(tenant_id);
CREATE INDEX idx_orders_tenant ON orders(tenant_id);
CREATE INDEX idx_orders_user ON orders(user_id);
```

#### Bridge Model Schema Template

```sql
-- For each tenant, create a dedicated schema
CREATE SCHEMA tenant_<tenant_id>;

-- Users table in tenant schema
CREATE TABLE tenant_<tenant_id>.users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Products table
CREATE TABLE tenant_<tenant_id>.products (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Orders table
CREATE TABLE tenant_<tenant_id>.orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES tenant_<tenant_id>.users(user_id),
    total_amount DECIMAL(10, 2),
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### DynamoDB Schema

```json
// Tenants Table
{
  "TableName": "tenants",
  "KeySchema": [
    { "AttributeName": "tenant_id", "KeyType": "HASH" }
  ],
  "AttributeDefinitions": [
    { "AttributeName": "tenant_id", "AttributeType": "S" },
    { "AttributeName": "email", "AttributeType": "S" }
  ],
  "GlobalSecondaryIndexes": [
    {
      "IndexName": "EmailIndex",
      "KeySchema": [
        { "AttributeName": "email", "KeyType": "HASH" }
      ],
      "Projection": { "ProjectionType": "ALL" }
    }
  ],
  "BillingMode": "PAY_PER_REQUEST"
}

// Item Structure
{
  "tenant_id": "uuid",
  "company_name": "string",
  "admin_email": "string",
  "tier": "pool|bridge|silo",
  "status": "provisioning|active|suspended",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "settings": {
    "features": ["feature1", "feature2"],
    "limits": {
      "users": 100,
      "storage_gb": 50
    }
  },
  "billing": {
    "plan": "basic|pro|enterprise",
    "mrr": 99.99
  }
}
```

---

## Data Flow

### Request Flow

```
1. Client Request
   └─> HTTPS to CloudFront
       └─> CloudFront CDN
           └─> API Gateway

2. Authentication
   └─> API Gateway Authorizer
       └─> Cognito User Pool
           └─> JWT Token Validation
               └─> Extract tenant_id from claims

3. Request Routing
   └─> Lambda Function
       └─> Extract tenant context
           └─> Apply tenant filter
               └─> Query database (tenant-scoped)

4. Data Access
   └─> RDS/DynamoDB
       └─> Row-level or schema-based filtering
           └─> Return tenant data only

5. Response
   └─> Lambda processes data
       └─> API Gateway formats response
           └─> CloudFront caches (if applicable)
               └─> Client receives response

Typical Latency: 50-150ms
```

### Tenant Onboarding Flow

```
1. Admin submits onboarding request
   └─> POST /tenants
       └─> {company_name, admin_email, tier}

2. Lambda: Tenant Onboarding
   ├─> Generate unique tenant_id
   ├─> Save to DynamoDB tenants table
   ├─> Provision resources based on tier:
   │   ├─> Pool: Add DB record
   │   ├─> Bridge: Create schema
   │   └─> Silo: Trigger IaC pipeline
   └─> Create admin user in Cognito
       └─> Send welcome email

3. Background Processing
   └─> Step Functions (for silo)
       ├─> Create VPC
       ├─> Create RDS instance
       ├─> Create Lambda functions
       ├─> Create API Gateway
       └─> Update tenant status to 'active'

4. Notification
   └─> SNS notification to admin
       └─> Email with login credentials
           └─> Tenant onboarding complete

Timeline:
- Pool: < 1 minute
- Bridge: 1-2 minutes
- Silo: 10-15 minutes
```

---

## Security Architecture

### Defense in Depth

```
Layer 1: Network Security
├─> VPC with private subnets
├─> Security groups (least privilege)
├─> NACLs for network-level filtering
└─> VPC endpoints for AWS services

Layer 2: Identity & Access
├─> Cognito for user authentication
├─> IAM roles for service-to-service
├─> JWT tokens with tenant context
└─> MFA enforcement (optional)

Layer 3: Application Security
├─> Tenant context validation on every request
├─> Input validation and sanitization
├─> SQL injection prevention (parameterized queries)
├─> XSS protection
└─> CORS policies

Layer 4: Data Security
├─> Encryption at rest (KMS)
├─> Encryption in transit (TLS 1.2+)
├─> Row-level security (RLS)
├─> Database encryption
└─> S3 bucket policies

Layer 5: Monitoring & Audit
├─> CloudWatch Logs (all API calls)
├─> CloudTrail (infrastructure changes)
├─> GuardDuty (threat detection)
├─> Security Hub (compliance)
└─> Config (resource compliance)
```

---

## Scaling Strategy

### Horizontal Scaling

```yaml
Lambda:
  Concurrency:
    Pool: 100-1000 per function
    Bridge: 500-2000 per function
    Silo: Unlimited (per tenant)
  
  Provisioned Concurrency:
    Pool: 10 (warm starts)
    Bridge: 20
    Silo: 50

RDS:
  Read Replicas:
    Pool: 2-3 replicas
    Bridge: 1-2 replicas
    Silo: Custom per tenant
  
  Auto Scaling:
    CPU: 70% threshold
    Connections: 80% threshold

DynamoDB:
  Auto Scaling:
    Target: 70% utilization
    Min: 5 RCU/WCU
    Max: 1000 RCU/WCU
```

### Performance Optimization

```yaml
Caching Strategy:
  API Gateway: 5 minutes TTL
  Lambda: In-memory caching
  RDS: Query result cache
  CloudFront: Static assets (24 hours)

Connection Pooling:
  RDS: PgBouncer or RDS Proxy
  Max Connections: 100 per Lambda

Batch Processing:
  DynamoDB: BatchWriteItem
  SQS: Message batching
  S3: Multipart uploads
```

---

This architecture provides a robust, scalable, and secure foundation for building multi-tenant SaaS applications on AWS.
