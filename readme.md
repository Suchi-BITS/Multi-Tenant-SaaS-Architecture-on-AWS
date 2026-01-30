# Multi-Tenant SaaS Architecture on AWS

A comprehensive guide and implementation of single-tenant vs multi-tenant cloud architectures using AWS services.

## Table of Contents
- [Overview](#overview)
- [Architecture Patterns](#architecture-patterns)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Deployment Guide](#deployment-guide)
- [Features](#features)
- [Security & Isolation](#security--isolation)
- [Cost Optimization](#cost-optimization)
- [Monitoring & Observability](#monitoring--observability)
- [Cleanup](#cleanup)

## Overview

This project demonstrates the implementation of both **single-tenant** and **multi-tenant** architectures on AWS, showcasing the key differences, trade-offs, and best practices for building scalable SaaS applications.

### What is Multi-Tenancy?

Multi-tenancy is an architecture where a single instance of software serves multiple customers (tenants). Each tenant's data is isolated and invisible to other tenants, while sharing the same application instance and infrastructure.

### Single-Tenant vs Multi-Tenant

| Aspect | Single-Tenant | Multi-Tenant |
|--------|---------------|--------------|
| **Resources** | Dedicated per tenant | Shared across tenants |
| **Isolation** | Complete isolation | Logical isolation |
| **Customization** | Highly customizable | Standardized with limited customization |
| **Cost** | Higher (dedicated resources) | Lower (economies of scale) |
| **Scalability** | Scale per tenant | Scale for all tenants together |
| **Security** | Enhanced (physical separation) | Good (logical separation) |
| **Maintenance** | Per-tenant updates | Single update for all |
| **Performance** | Predictable | May have noisy neighbor issues |

## Architecture Patterns

### Multi-Tenant Models

This project implements three multi-tenant isolation models:

#### 1. **Pool Model** (Basic Tier)
- All tenants share the same infrastructure
- Most cost-effective
- Suitable for small businesses with similar workloads
- Uses row-level security for data isolation

```
┌─────────────────────────────────────┐
│         Application Layer           │
│   (Shared API Gateway + Lambda)     │
└─────────────────────────────────────┘
              │
┌─────────────────────────────────────┐
│      Shared Database Instance        │
│  ┌─────┬─────┬─────┬─────┬─────┐   │
│  │Tnt A│Tnt B│Tnt C│Tnt D│Tnt E│   │
│  └─────┴─────┴─────┴─────┴─────┘   │
└─────────────────────────────────────┘
```

#### 2. **Bridge Model** (Standard Tier)
- Shared compute, isolated databases
- Balanced approach between cost and isolation
- Each tenant gets their own database schema

```
┌─────────────────────────────────────┐
│         Application Layer           │
│   (Shared API Gateway + Lambda)     │
└─────────────────────────────────────┘
         │              │
┌────────────┐   ┌────────────┐
│ Database   │   │ Database   │
│  Tenant A  │   │  Tenant B  │
└────────────┘   └────────────┘
```

#### 3. **Silo Model** (Premium Tier)
- Completely isolated infrastructure per tenant
- Maximum security and customization
- Dedicated compute, storage, and databases

```
┌──────────────────────┐  ┌──────────────────────┐
│   Tenant A Stack     │  │   Tenant B Stack     │
│  ┌──────┐ ┌──────┐  │  │  ┌──────┐ ┌──────┐  │
│  │Lambda│ │  RDS │  │  │  │Lambda│ │  RDS │  │
│  └──────┘ └──────┘  │  │  └──────┘ └──────┘  │
└──────────────────────┘  └──────────────────────┘
```

## Project Structure

```
multi-tenant-saas-aws/
├── README.md
├── architecture/
│   ├── pool-model/          # Pool model implementation
│   ├── bridge-model/        # Bridge model implementation
│   └── silo-model/          # Silo model implementation
├── infrastructure/
│   ├── terraform/           # Terraform IaC
│   │   ├── modules/
│   │   │   ├── vpc/
│   │   │   ├── compute/
│   │   │   ├── database/
│   │   │   └── api-gateway/
│   │   ├── environments/
│   │   │   ├── pool/
│   │   │   ├── bridge/
│   │   │   └── silo/
│   │   └── main.tf
│   └── cloudformation/      # CloudFormation templates
├── application/
│   ├── lambda-functions/
│   │   ├── tenant-onboarding/
│   │   ├── user-management/
│   │   ├── product-service/
│   │   └── order-service/
│   ├── layers/
│   │   ├── tenant-context/
│   │   ├── logging/
│   │   └── metrics/
│   └── api/
├── scripts/
│   ├── deploy.sh
│   ├── setup-tenant.sh
│   ├── cleanup.sh
│   └── test-apis.sh
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── API_REFERENCE.md
│   └── TROUBLESHOOTING.md
└── tests/
    ├── integration/
    └── load-tests/
```

##  Prerequisites

### Required Tools
- **AWS CLI** (v2.x or higher)
  ```bash
  aws --version
  ```
- **Terraform** (v1.0 or higher)
  ```bash
  terraform --version
  ```
- **Node.js** (v18 or higher)
  ```bash
  node --version
  ```
- **Python** (v3.9 or higher)
  ```bash
  python --version
  ```
- **Docker** (for local testing)
  ```bash
  docker --version
  ```

### AWS Account Setup
1. AWS Account with administrative access
2. AWS CLI configured with credentials
   ```bash
   aws configure
   ```
3. Sufficient service quotas for:
   - VPCs (minimum 3)
   - EC2 instances
   - RDS databases
   - Lambda functions
   - API Gateway APIs

### Required AWS Services
- Amazon VPC
- Amazon API Gateway
- AWS Lambda
- Amazon RDS (PostgreSQL)
- Amazon DynamoDB
- Amazon Cognito
- AWS IAM
- Amazon CloudWatch
- AWS CodePipeline
- Amazon S3
- AWS Systems Manager (Parameter Store)

##  Deployment Guide

### Quick Start

1. **Clone the Repository**
   ```bash
   git clone <your-repo-url>
   cd multi-tenant-saas-aws
   ```

2. **Set Environment Variables**
   ```bash
   export AWS_REGION=us-east-1
   export ENVIRONMENT=dev
   export ADMIN_EMAIL=your-email@example.com
   ```

3. **Deploy Infrastructure**
   ```bash
   cd infrastructure/terraform
   
   # Initialize Terraform
   terraform init
   
   # Review the plan
   terraform plan -var="admin_email=$ADMIN_EMAIL"
   
   # Apply the configuration
   terraform apply -var="admin_email=$ADMIN_EMAIL"
   ```

4. **Deploy Application**
   ```bash
   cd ../../scripts
   ./deploy.sh --environment dev
   ```

### Deployment by Model

#### Pool Model Deployment
```bash
cd infrastructure/terraform/environments/pool
terraform init
terraform apply -var="tenant_tier=pool"
```

#### Bridge Model Deployment
```bash
cd infrastructure/terraform/environments/bridge
terraform init
terraform apply -var="tenant_tier=bridge"
```

#### Silo Model Deployment
```bash
cd infrastructure/terraform/environments/silo
terraform init
terraform apply -var="tenant_tier=silo" -var="tenant_id=tenant-001"
```

### Post-Deployment Configuration

1. **Create Admin User**
   ```bash
   ./scripts/create-admin-user.sh
   ```

2. **Onboard First Tenant**
   ```bash
   ./scripts/setup-tenant.sh --name "Demo Tenant" --tier pool
   ```

3. **Test API Endpoints**
   ```bash
   ./scripts/test-apis.sh
   ```

##  Features

### Tenant Management
- **Automated Onboarding**: Self-service tenant provisioning
- **Tier-based Deployment**: Automatic resource allocation based on tier
- **User Management**: Cognito-based authentication and authorization
- **Tenant Isolation**: Row-level security and IAM policies

### Security Features
- **Data Isolation**: Multiple strategies (DB, schema, row-level)
- **Authentication**: Amazon Cognito user pools
- **Authorization**: JWT-based with tenant context
- **Encryption**: At-rest and in-transit encryption
- **Compliance**: Audit logging and compliance reporting

### Observability
- **Tenant-aware Logging**: CloudWatch Logs with tenant context
- **Metrics Collection**: Custom CloudWatch metrics per tenant
- **Cost Tracking**: Per-tenant cost allocation
- **Performance Monitoring**: X-Ray distributed tracing

### Scalability
- **Auto-scaling**: Lambda and RDS auto-scaling
- **Load Balancing**: Application Load Balancer
- **Caching**: ElastiCache for session and data caching
- **CDN**: CloudFront for static content delivery

##  Security & Isolation

### Data Isolation Strategies

#### 1. Row-Level Security (Pool Model)
```sql
-- PostgreSQL RLS policy example
CREATE POLICY tenant_isolation_policy ON orders
    USING (tenant_id = current_setting('app.current_tenant')::uuid);
```

#### 2. Schema-based Isolation (Bridge Model)
```sql
-- Each tenant gets their own schema
CREATE SCHEMA tenant_abc;
CREATE TABLE tenant_abc.orders (...);
```

#### 3. Database-level Isolation (Silo Model)
```
Each tenant gets a dedicated RDS instance
```

### IAM Policies

#### Tenant-scoped Policy Example
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/TenantData",
      "Condition": {
        "ForAllValues:StringEquals": {
          "dynamodb:LeadingKeys": ["${aws:userid}"]
        }
      }
    }
  ]
}
```

### Authentication Flow
```
1. User → Login Request → API Gateway
2. API Gateway → Cognito User Pool → Verify Credentials
3. Cognito → Return JWT with tenant context
4. User → API Request with JWT → Lambda
5. Lambda → Extract tenant ID from JWT
6. Lambda → Scope database query to tenant
7. Lambda → Return tenant-specific data
```

##  Cost Optimization

### Cost Allocation Strategy

1. **Resource Tagging**
   ```hcl
   tags = {
     TenantId    = var.tenant_id
     Environment = var.environment
     CostCenter  = var.cost_center
     Tier        = var.tenant_tier
   }
   ```

2. **Cost Tracking per Tenant**
   - Use AWS Cost Allocation Tags
   - CloudWatch custom metrics for usage tracking
   - Lambda for cost calculation and reporting

3. **Serverless Cost Benefits**
   - Pay per request with Lambda
   - Aurora Serverless for variable workloads
   - DynamoDB on-demand pricing

### Cost Comparison (Monthly Estimates)

| Model | Small Tenant | Medium Tenant | Large Tenant |
|-------|--------------|---------------|--------------|
| **Pool** | $50-100 | $100-200 | $200-400 |
| **Bridge** | $150-300 | $300-600 | $600-1200 |
| **Silo** | $500-1000 | $1000-2000 | $2000-5000 |

##  Monitoring & Observability

### CloudWatch Dashboards

#### Tenant-specific Dashboard
```javascript
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Lambda", "Invocations", {"stat": "Sum"}],
          [".", "Errors", {"stat": "Sum"}],
          [".", "Duration", {"stat": "Average"}]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Lambda Metrics - Tenant ABC",
        "dimensions": {
          "TenantId": "tenant-abc"
        }
      }
    }
  ]
}
```

### Logging Strategy

#### Structured Logging Example
```python
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def log_with_context(tenant_id, event, message):
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'tenant_id': tenant_id,
        'event': event,
        'message': message,
        'level': 'INFO'
    }
    logger.info(json.dumps(log_entry))
```

### Metrics Collection

#### Custom Metrics Example
```python
import boto3

cloudwatch = boto3.client('cloudwatch')

def publish_tenant_metric(tenant_id, metric_name, value):
    cloudwatch.put_metric_data(
        Namespace='MultiTenantSaaS',
        MetricData=[
            {
                'MetricName': metric_name,
                'Value': value,
                'Unit': 'Count',
                'Dimensions': [
                    {
                        'Name': 'TenantId',
                        'Value': tenant_id
                    }
                ]
            }
        ]
    )
```

##  Cleanup

### Complete Cleanup
```bash
# Destroy Terraform resources
cd infrastructure/terraform
terraform destroy -auto-approve

# Clean up S3 buckets
aws s3 rb s3://your-bucket-name --force

# Delete CloudWatch Log Groups
aws logs delete-log-group --log-group-name /aws/lambda/tenant-function

# Remove parameter store values
aws ssm delete-parameter --name /multitenant/config
```

### Tenant-specific Cleanup
```bash
./scripts/cleanup.sh --tenant-id tenant-001
```

##  Additional Resources

- [AWS SaaS Factory](https://aws.amazon.com/partners/programs/saas-factory/)
- [AWS Well-Architected SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/saas-lens.html)
- [Multi-tenancy Best Practices](https://aws.amazon.com/blogs/architecture/lets-architect-building-multi-tenant-saas-systems/)
- [AWS SaaS Builder Toolkit](https://github.com/awslabs/sbt-aws)

##  Contributing

Contributions are welcome! Please read our contributing guidelines and submit pull requests.

##  License

This project is licensed under the MIT License - see the LICENSE file for details.

##  Support

For issues and questions:
- Open an issue on GitHub
- Contact: support@example.com
- Documentation: [docs/](./docs/)

##  Learning Path

1. Start with the [Architecture Documentation](./docs/ARCHITECTURE.md)
2. Follow the [Deployment Guide](./docs/DEPLOYMENT.md)
3. Explore [API Reference](./docs/API_REFERENCE.md)
4. Review [Troubleshooting Guide](./docs/TROUBLESHOOTING.md)

---

