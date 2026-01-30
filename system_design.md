# Architecture Documentation

## System Architecture Overview

This AWS Serverless SaaS application implements a comprehensive multi-tenant architecture using AWS managed services. The system is designed to handle multiple tenants with strong isolation, scalability, and observability.

## Architecture Diagram

```
┌─────────────┐
│   Client    │
│  (React)    │
└──────┬──────┘
       │
       │ HTTPS
       ▼
┌─────────────────────────────────┐
│      Amazon CloudFront          │
│     (Static Content CDN)        │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│      Amazon API Gateway         │
│   - REST API                    │
│   - Cognito Authorizer          │
│   - Request/Response Transform  │
└─────────────┬───────────────────┘
              │
              ├─────────────────┐
              │                 │
              ▼                 ▼
┌─────────────────┐   ┌─────────────────┐
│  Amazon Cognito │   │  AWS Lambda     │
│  - User Pools   │   │  Functions      │
│  - Groups       │   │  - Auth         │
│  - JWT Tokens   │   │  - Tenant       │
└─────────────────┘   │  - Product      │
                      │  - Order        │
                      └────────┬────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │  Amazon         │
                      │  DynamoDB       │
                      │  - Tenants      │
                      │  - Products     │
                      │  - Orders       │
                      └─────────────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │  Amazon         │
                      │  CloudWatch     │
                      │  - Logs         │
                      │  - Metrics      │
                      │  - Alarms       │
                      └─────────────────┘
```

## Core Components

### 1. Frontend (React Application)

**Location**: `/client`

**Purpose**: Single-page application providing user interface

**Key Features**:
- React 18 with React Router
- Responsive design
- JWT token management
- Automatic token refresh
- Tenant-aware UI

**Pages**:
- Login/Registration
- Dashboard (statistics overview)
- Products (CRUD operations)
- Orders (management)
- Settings (tenant configuration)

### 2. API Gateway

**Purpose**: Central entry point for all API requests

**Configuration**:
- REST API with resource-based routing
- Cognito authorizer for authentication
- CORS enabled for web clients
- Request/response transformations
- Rate limiting per tenant

**Endpoints**:
```
POST   /tenants              - Register tenant
GET    /tenants/{id}         - Get tenant info
PUT    /tenants/{id}         - Update tenant
DELETE /tenants/{id}         - Delete tenant

POST   /auth/signup          - User registration
POST   /auth/signin          - User login
POST   /auth/refresh         - Refresh token
POST   /auth/signout         - Logout

GET    /products             - List products
GET    /products/{id}        - Get product
POST   /products             - Create product
PUT    /products/{id}        - Update product
DELETE /products/{id}        - Delete product

GET    /orders               - List orders
GET    /orders/{id}          - Get order
POST   /orders               - Create order
PUT    /orders/{id}          - Update order
```

### 3. AWS Lambda Functions

**Location**: `/server`

**Runtime**: Python 3.9

**Architecture Pattern**: Microservices

Each service is implemented as a separate Lambda function:

#### Auth Service
- User registration with tenant association
- Login with JWT token generation
- Token refresh
- Password reset

#### Tenant Service
- Tenant onboarding (automated provisioning)
- Configuration management
- Tier management (basic, premium, enterprise)
- Tenant deletion (soft delete with cleanup)

#### Product Service
- Full CRUD operations
- Pagination support
- Tenant isolation enforcement
- Tier-based limits

#### Order Service
- Order creation and management
- Status workflow (pending → confirmed → shipped → delivered)
- Event publishing (SNS)
- Revenue tracking

**Shared Layer**:
- `tenant_utils.py`: Common utilities
- Tenant context management
- Logging and metrics
- DynamoDB connection pooling

### 4. Amazon Cognito

**Purpose**: Identity and access management

**Configuration**:
- User Pool for authentication
- Custom attributes: `tenant_id`, `tenant_tier`
- User Pool Groups per tenant
- Password policies
- Email verification
- MFA support (optional)

**Token Structure**:
```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "custom:tenant_id": "tenant-uuid",
  "custom:tenant_tier": "premium",
  "cognito:groups": ["tenant-xyz"]
}
```

### 5. Amazon DynamoDB

**Purpose**: Primary data store with tenant isolation

#### Isolation Models

**Pool Model** (Shared Tables):
```
Table: products
Primary Key: tenant_id (HASH), product_id (RANGE)

Table: orders
Primary Key: tenant_id (HASH), order_id (RANGE)
```

**Silo Model** (Dedicated Tables):
```
Table: products-{tenant-id}
Primary Key: product_id (HASH)

Table: orders-{tenant-id}
Primary Key: order_id (HASH)
```

#### Table Designs

**Tenants Table**:
```
{
  "tenant_id": "uuid",
  "company_name": "string",
  "admin_email": "string",
  "tier": "basic|premium|enterprise",
  "isolation_model": "pool|silo",
  "status": "active|suspended|deleted",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "limits": {
    "max_products": 100,
    "max_orders": 1000,
    "max_users": 10
  },
  "features": {
    "advanced_analytics": false,
    "custom_branding": false,
    "api_access": true
  }
}
```

**Products Table**:
```
{
  "tenant_id": "uuid",         # Only in pool model
  "product_id": "uuid",
  "name": "string",
  "description": "string",
  "price": "decimal",
  "category": "string",
  "sku": "string",
  "inventory": "number",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

**Orders Table**:
```
{
  "tenant_id": "uuid",         # Only in pool model
  "order_id": "uuid",
  "customer_email": "string",
  "items": [
    {
      "product_id": "uuid",
      "product_name": "string",
      "quantity": "number",
      "price": "decimal",
      "subtotal": "decimal"
    }
  ],
  "total_amount": "decimal",
  "status": "pending|confirmed|shipped|delivered|cancelled",
  "shipping_address": {
    "street": "string",
    "city": "string",
    "state": "string",
    "zip": "string"
  },
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### 6. Amazon CloudWatch

**Purpose**: Monitoring, logging, and observability

**Components**:

#### Logs
- Centralized logging per Lambda function
- Tenant-specific log streams
- Structured logging (JSON format)
- 7-day retention (configurable)

#### Metrics
- Custom metrics per tenant:
  - API call count
  - Error rate
  - Latency
  - Resource usage

#### Dashboards
- Real-time tenant activity
- System health overview
- Performance metrics
- Cost tracking

#### Alarms
- High error rates
- Latency thresholds
- Resource limits
- Security events

### 7. Amazon SNS

**Purpose**: Event-driven communication

**Use Cases**:
- Order status notifications
- Tenant lifecycle events
- System alerts
- Async processing triggers

## Data Flow

### 1. User Authentication Flow

```
User → API Gateway → Auth Lambda → Cognito
                                     ↓
User ← API Gateway ← Auth Lambda ← JWT Tokens
```

### 2. Product Creation Flow

```
User → API Gateway (with JWT) → Cognito (validate)
                                     ↓
                            Product Lambda
                                     ↓
                            Extract tenant_id from JWT
                                     ↓
                            Check tenant limits
                                     ↓
                            DynamoDB (tenant-partitioned)
                                     ↓
                            CloudWatch (log + metrics)
                                     ↓
User ← API Gateway ← Success Response
```

### 3. Order Processing Flow

```
User → Create Order → Order Lambda
                           ↓
                     Validate items
                           ↓
                     Calculate total
                           ↓
                     Store in DynamoDB
                           ↓
                     Publish to SNS
                           ↓
                  ┌────────┴────────┐
                  ▼                 ▼
            Email Service    Inventory Service
```

## Security Architecture

### 1. Authentication
- Cognito-based JWT tokens
- Token expiration (1 hour)
- Refresh token rotation
- MFA support

### 2. Authorization
- API Gateway Cognito authorizer
- Tenant ID in JWT claims
- Lambda validates tenant access
- IAM roles with least privilege

### 3. Tenant Isolation

**Compute Isolation**:
- JWT token contains tenant_id
- All Lambda functions extract and validate
- Tenant context passed through request lifecycle

**Data Isolation**:
- Pool model: Tenant ID in partition key
- Silo model: Dedicated tables per tenant
- Queries always filtered by tenant_id

**Enforcement**:
```python
# Every data access validates tenant
if request_tenant_id != resource_tenant_id:
    raise TenantIsolationError
```

### 4. Encryption
- DynamoDB encryption at rest
- TLS 1.2+ for all communication
- Cognito encrypted credentials

## Scalability

### Horizontal Scaling
- Lambda: Auto-scales to 1000 concurrent executions
- DynamoDB: On-demand capacity mode
- API Gateway: Handles any request volume

### Performance Optimization
- Lambda: Warmed containers with provisioned concurrency
- DynamoDB: DAX caching for hot data
- CloudFront: CDN for static content
- Connection pooling in Lambda layers

## Cost Optimization

### Pay-per-use
- Lambda: Charged per invocation and duration
- DynamoDB: Pay for actual read/write operations
- API Gateway: Per request pricing

### Tier-based Resource Allocation
- Basic: On-demand capacity
- Premium: Provisioned capacity
- Enterprise: Reserved capacity

### Monitoring
- Cost allocation tags per tenant
- Budget alerts
- Usage tracking per tenant

## Disaster Recovery

### Backup Strategy
- DynamoDB: Point-in-time recovery enabled
- Lambda: Code in S3 with versioning
- Cognito: User pool backup (export)

### Multi-Region Support
- CloudFormation templates for multi-region
- DynamoDB Global Tables
- Route 53 for failover

## Observability

### Metrics Collection
```python
cloudwatch.put_metric_data(
    Namespace='SaaSApplication',
    MetricData=[{
        'MetricName': 'TenantAPICall',
        'Value': 1,
        'Dimensions': [
            {'Name': 'TenantId', 'Value': tenant_id},
            {'Name': 'TenantTier', 'Value': tier}
        ]
    }]
)
```

### Logging Pattern
```json
{
  "timestamp": "2025-01-30T12:00:00Z",
  "tenant_id": "tenant-123",
  "tenant_tier": "premium",
  "function": "create_product",
  "status": "SUCCESS",
  "duration_ms": 150,
  "request_id": "abc-123"
}
```

### Tracing
- AWS X-Ray integration
- End-to-end request tracking
- Performance bottleneck identification

## Best Practices Implemented

1. **Tenant Isolation**: Every operation validates tenant access
2. **Least Privilege**: IAM roles with minimal permissions
3. **Idempotency**: All APIs support idempotent operations
4. **Error Handling**: Graceful degradation and retry logic
5. **Monitoring**: Comprehensive logging and metrics
6. **Documentation**: API documentation with examples
7. **Testing**: Unit, integration, and load tests
8. **CI/CD**: Automated deployment pipeline
9. **Versioning**: API versioning support
10. **Compliance**: GDPR and data residency considerations
