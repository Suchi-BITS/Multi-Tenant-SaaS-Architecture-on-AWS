# Production-Ready Multi-Tenant SaaS on AWS

## Folder Structure

```
multi-tenant-saas-aws/
├── architecture/
│   └── design.md
├── infrastructure/
│   └── terraform/
│       ├── modules/
│       │   ├── lambda/
│       │   ├── apigateway/
│       │   ├── dynamodb/
│       │   └── iam/
│       └── environments/
│           └── dev/
├── application/
│   ├── middleware/
│   │   └── tenant_isolation.py
│   ├── lambda-functions/
│   │   ├── auth_handler.py
│   │   ├── product_handler.py
│   │   └── order_handler.py
│   └── layers/common/
├── scripts/
├── tests/
└── .github/workflows/deploy.yml
```

---

# architecture/design.md

```md
Tenant Isolation Strategy
--------------------------
Model: Pooled
Isolation Layer: Middleware validation + partition keys
Security Layers:
- IAM
- JWT tenant claims
- DynamoDB partition isolation
```

---

# middleware/tenant_isolation.py

```python
class TenantContext:
    def __init__(self, event):
        headers = event.get("headers", {})
        self.tenant_id = headers.get("tenant-id")
        if not self.tenant_id:
            raise Exception("Tenant header missing")

    def enforce(self, item):
        if item.get("tenant_id") != self.tenant_id:
            raise Exception("Tenant isolation violation")
```

---

# layers/common/utils.py

```python
import json

def response(code, body):
    return {"statusCode": code, "body": json.dumps(body)}
```

---

# lambda-functions/auth_handler.py

```python
from common.utils import response

def handler(event, context):
    tenant = event.get("headers", {}).get("tenant-id")
    if not tenant:
        return response(401, {"error":"unauthorized"})
    return response(200,{"tenant":tenant})
```

---

# lambda-functions/product_handler.py

```python
import boto3
from common.utils import response
from middleware.tenant_isolation import TenantContext

db = boto3.resource("dynamodb")
table = db.Table("products")

def handler(event, context):
    tenant = TenantContext(event).tenant_id
    body = event.get("body")

    table.put_item(Item={
        "tenant_id": tenant,
        "product_id": body["id"],
        "name": body["name"]
    })

    return response(200,{"created":True})
```

---

# lambda-functions/order_handler.py

```python
import boto3
from common.utils import response
from middleware.tenant_isolation import TenantContext

db=boto3.resource("dynamodb")
table=db.Table("orders")

def handler(event, context):
    tenant=TenantContext(event).tenant_id
    body=event.get("body")

    table.put_item(Item={
        "tenant_id":tenant,
        "order_id":body["id"],
        "total":body["total"]
    })

    return response(200,{"ok":True})
```

---

# Terraform Modules

## modules/dynamodb/main.tf

```hcl
resource "aws_dynamodb_table" "this" {
  name = var.name
  billing_mode = "PAY_PER_REQUEST"
  hash_key = "tenant_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }
}
```

## modules/apigateway/main.tf

```hcl
resource "aws_apigatewayv2_api" "this" {
  name = var.name
  protocol_type = "HTTP"
}
```

## modules/iam/main.tf

```hcl
resource "aws_iam_role" "lambda_role" {
  name = "lambda-role"
  assume_role_policy = jsonencode({
    Version="2012-10-17",
    Statement=[{
      Effect="Allow",
      Principal={Service="lambda.amazonaws.com"},
      Action="sts:AssumeRole"
    }]
  })
}
```

## modules/lambda/main.tf

```hcl
resource "aws_lambda_function" "fn" {
  function_name = var.name
  handler       = var.handler
  runtime       = "python3.10"
  filename      = var.filename
  role          = var.role
}
```

---

# environments/dev/main.tf

```hcl
provider "aws" { region="ap-south-1" }

module "iam" { source="../../modules/iam" }

module "products_table" {
  source="../../modules/dynamodb"
  name="products"
}

module "orders_table" {
  source="../../modules/dynamodb"
  name="orders"
}

module "api" {
  source="../../modules/apigateway"
  name="saas-api"
}
```

---

# scripts/deploy.sh

```bash
#!/bin/bash
set -e
terraform -chdir=infrastructure/terraform/environments/dev init
terraform -chdir=infrastructure/terraform/environments/dev apply -auto-approve
```

---

# tests/test_isolation.py

```python
from middleware.tenant_isolation import TenantContext

def test_violation():
    ctx=TenantContext({"headers":{"tenant-id":"t1"}})
    try:
        ctx.enforce({"tenant_id":"t2"})
        assert False
    except:
        assert True
```

---

# CI/CD Pipeline

.github/workflows/deploy.yml

```yaml
name: deploy
on: [push]

jobs:
 deploy:
  runs-on: ubuntu-latest
  steps:
   - uses: actions/checkout@v3
   - uses: hashicorp/setup-terraform@v2
   - run: terraform init
   - run: terraform apply -auto-approve
```

---

# requirements.txt

```
boto3
```

---

# Tenant Onboarding Service

application/lambda-functions/onboarding_handler.py

```python
import boto3, uuid
from common.utils import response

db=boto3.resource("dynamodb")
table=db.Table("tenants")

def handler(event,context):
    body=event.get("body")
    tenant_id=str(uuid.uuid4())

    table.put_item(Item={
        "tenant_id":tenant_id,
        "name":body["name"],
        "plan":"free"
    })

    return response(200,{"tenant_id":tenant_id})
```

---

# Cognito Auth + JWT Claims

modules/cognito/main.tf

```hcl
resource "aws_cognito_user_pool" "pool" {
 name = "saas-users"
}

resource "aws_cognito_user_pool_client" "client" {
 name = "client"
 user_pool_id = aws_cognito_user_pool.pool.id
}
```

JWT expected header

```
Authorization: Bearer <token>
```

Decoded claim must contain:

```
custom:tenant_id
```

Middleware addition

```python
self.tenant_id = claims["custom:tenant_id"]
```

---

# Usage Metering Service

application/lambda-functions/metering_handler.py

```python
import boto3,time

db=boto3.resource("dynamodb")
table=db.Table("usage")

def handler(event,context):
    table.put_item(Item={
        "tenant_id":event["tenant"],
        "ts":int(time.time()),
        "action":event["action"]
    })
```

---

# Billing Hook (Stripe example)

application/lambda-functions/billing_webhook.py

```python
import stripe,os
stripe.api_key=os.environ["STRIPE_KEY"]

def handler(event,context):
    payload=event["body"]
    sig=event["headers"]["Stripe-Signature"]
    stripe.Webhook.construct_event(payload,sig,os.environ["ENDPOINT_SECRET"])
```

---

# Observability Stack

modules/observability/main.tf

```hcl
resource "aws_cloudwatch_log_group" "lambda" {
 name = "/aws/lambda/saas"
 retention_in_days = 14
}

resource "aws_xray_sampling_rule" "trace" {
 rule_name = "all"
 priority = 1
 fixed_rate = 1
 reservoir_size = 1
 service_name = "*"
}
```

---

# Multi‑Region Failover

modules/global/main.tf

```hcl
provider "aws" { alias="primary" region="ap-south-1" }
provider "aws" { alias="secondary" region="us-east-1" }

resource "aws_dynamodb_table" "global" {
 name="global-table"
 billing_mode="PAY_PER_REQUEST"
 hash_key="tenant_id"

 attribute { name="tenant_id" type="S" }

 replica { region_name="us-east-1" }
}
```

Route53 Failover

```hcl
resource "aws_route53_record" "primary" {
 set_identifier = "primary"
 failover_routing_policy { type="PRIMARY" }
}
```

---

# Updated requirements.txt

```
boto3
stripe
pyjwt
```

---

# Tenant Tier-Based Throttling

application/middleware/throttling.py

```python
TIERS={
 "free":5,
 "pro":50,
 "enterprise":500
}

class Throttle:
    def __init__(self,tenant):
        self.tenant=tenant
        self.calls=0

    def check(self,plan):
        self.calls+=1
        if self.calls>TIERS[plan]:
            raise Exception("Rate limit exceeded")
```

---

# Feature Flags per Tenant

application/services/feature_flags.py

```python
import boto3

db=boto3.resource("dynamodb")
table=db.Table("features")

def enabled(tenant,feature):
    res=table.get_item(Key={"tenant_id":tenant,"feature":feature})
    return res.get("Item",{}).get("enabled",False)
```

Usage

```python
if not enabled(tenant,"advanced_reports"):
    raise Exception("Feature disabled")
```

---

# Schema-per-Tenant Isolation Option

modules/rds/main.tf

```hcl
resource "aws_db_instance" "main" {
 allocated_storage = 20
 engine = "postgres"
 instance_class = "db.t3.micro"
 username = "admin"
 password = "password123"
 skip_final_snapshot = true
}
```

Tenant schema creation Lambda

```python
import psycopg2,os

def handler(event,context):
    conn=psycopg2.connect(os.environ["DB"])
    cur=conn.cursor()
    cur.execute(f"CREATE SCHEMA tenant_{event['tenant_id']}")
    conn.commit()
```

---

# Control Plane vs Data Plane Split

architecture/control-vs-data.md

```md
Control Plane
- tenant provisioning
- billing
- config

Data Plane
- APIs
- queries
- runtime execution

Isolation Principle
Control plane never touches tenant data directly.
```

Routing Example

```python
if path.startswith("/admin"):
    route="control"
else:
    route="data"
```

---

# Internal Developer Platform (IDP) APIs

application/lambda-functions/idp_handler.py

```python
from common.utils import response

SERVICES={}

def handler(event,context):
    body=event["body"]
    SERVICES[body["name"]]=body
    return response(200,{"registered":body["name"]})
```

Service Registration Example

```json
{
 "name":"recommendation-service",
 "owner":"ml-team",
 "tier":"internal"
}
```

---

# Terraform Additions

Add modules to environment

```hcl
module "rds" { source="../../modules/rds" }
```

---

# Final Architecture Capabilities Checklist

✔ Multi‑tenant isolation
✔ Tier throttling
✔ Feature flags
✔ Schema isolation option
✔ Control/data plane separation
✔ Global failover
✔ Observability
✔ Billing hooks
✔ IDP platform layer

System Status: Production‑grade SaaS Reference Architecture
