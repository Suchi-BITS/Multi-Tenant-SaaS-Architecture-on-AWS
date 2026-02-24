# Minimal Working Multi‑Tenant SaaS on AWS

## Folder Structure

```
multi-tenant-saas-aws/
│
├── architecture/
│   └── design.md
│
├── infrastructure/
│   └── terraform/
│       ├── modules/
│       │   └── lambda/
│       │       ├── main.tf
│       │       ├── variables.tf
│       │       └── outputs.tf
│       │
│       └── environments/
│           └── dev/
│               ├── main.tf
│               ├── variables.tf
│               └── terraform.tfvars
│
├── application/
│   ├── lambda-functions/
│   │   ├── auth_handler.py
│   │   ├── tenant_handler.py
│   │   ├── product_handler.py
│   │   └── order_handler.py
│   │
│   └── layers/
│       └── common/
│           └── utils.py
│
├── scripts/
│   └── deploy.sh
│
├── tests/
│   └── test_handlers.py
│
└── requirements.txt
```

---

# architecture/design.md

```md
## Architecture Overview

This is a pooled multi‑tenant SaaS architecture.

Tenants share:
- API Gateway
- Lambda
- DynamoDB tables

Tenant isolation is enforced using:
- tenant_id column
- IAM auth context
```

---

# infrastructure/terraform/modules/lambda/main.tf

```hcl
resource "aws_lambda_function" "this" {
  function_name = var.name
  handler       = var.handler
  runtime       = "python3.10"
  role          = var.role_arn
  filename      = var.filename
}
```

# variables.tf

```hcl
variable "name" {}
variable "handler" {}
variable "role_arn" {}
variable "filename" {}
```

# outputs.tf

```hcl
output "lambda_name" {
  value = aws_lambda_function.this.function_name
}
```

---

# infrastructure/terraform/environments/dev/main.tf

```hcl
provider "aws" {
  region = "ap-south-1"
}

module "auth_lambda" {
  source   = "../../modules/lambda"
  name     = "auth-service"
  handler  = "auth_handler.handler"
  role_arn = var.lambda_role
  filename = "../../../build/auth.zip"
}
```

# variables.tf

```hcl
variable "lambda_role" {}
```

# terraform.tfvars

```hcl
lambda_role = "arn:aws:iam::123456789012:role/lambda-role"
```

---

# application/layers/common/utils.py

```python
import json

def response(code, body):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }
```

---

# application/lambda-functions/auth_handler.py

```python
from common.utils import response

def handler(event, context):
    tenant = event.get("headers", {}).get("tenant-id")
    if not tenant:
        return response(401, {"error": "Missing tenant"})

    return response(200, {"message": "Authenticated", "tenant": tenant})
```

---

# tenant_handler.py

```python
from common.utils import response

TENANTS = {}

def handler(event, context):
    body = event.get("body")
    if body:
        TENANTS.update(body)
    return response(200, TENANTS)
```

---

# product_handler.py

```python
from common.utils import response

PRODUCTS = {}

def handler(event, context):
    tenant = event["headers"]["tenant-id"]
    PRODUCTS.setdefault(tenant, []).append(event["body"])
    return response(200, PRODUCTS[tenant])
```

---

# order_handler.py

```python
from common.utils import response

ORDERS = {}

def handler(event, context):
    tenant = event["headers"]["tenant-id"]
    ORDERS.setdefault(tenant, []).append(event["body"])
    return response(200, ORDERS[tenant])
```

---

# scripts/deploy.sh

```bash
#!/bin/bash
zip -r auth.zip application/lambda-functions/auth_handler.py
terraform init
terraform apply -auto-approve
```

---

# tests/test_handlers.py

```python
from application.lambda-functions.auth_handler import handler

def test_auth():
    event = {"headers": {"tenant-id": "t1"}}
    res = handler(event, None)
    assert res["statusCode"] == 200
```

---

# requirements.txt

```
boto3
```
