# Compute Module - Lambda Functions and API Gateway Configuration

variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Lambda"
  type        = list(string)
}

variable "lambda_security_group_id" {
  description = "Security group ID for Lambda functions"
  type        = string
}

variable "tenant_tier" {
  description = "Tenant tier"
  type        = string
}

variable "db_secret_arn" {
  description = "Database secret ARN"
  type        = string
}

variable "cognito_user_pool_arn" {
  description = "Cognito User Pool ARN"
  type        = string
}

variable "tags" {
  description = "Tags to apply"
  type        = map(string)
  default     = {}
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_execution" {
  name = "${var.project_name}-${var.environment}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# IAM Policy for Lambda
resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-${var.environment}-lambda-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:AssignPrivateIpAddresses",
          "ec2:UnassignPrivateIpAddresses"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.db_secret_arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminGetUser",
          "cognito-idp:AdminUpdateUserAttributes",
          "cognito-idp:AdminDeleteUser"
        ]
        Resource = var.cognito_user_pool_arn
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      }
    ]
  })
}

# Lambda Layer for shared dependencies
resource "aws_lambda_layer_version" "tenant_context" {
  filename            = "${path.module}/../../../application/layers/tenant-context/tenant-context-layer.zip"
  layer_name          = "${var.project_name}-tenant-context"
  compatible_runtimes = ["python3.9", "python3.10", "python3.11"]
  description         = "Tenant context utilities"

  source_code_hash = fileexists("${path.module}/../../../application/layers/tenant-context/tenant-context-layer.zip") ? filebase64sha256("${path.module}/../../../application/layers/tenant-context/tenant-context-layer.zip") : null

  tags = var.tags
}

# Tenant Onboarding Lambda
resource "aws_lambda_function" "tenant_onboarding" {
  filename         = "${path.module}/../../../application/lambda-functions/tenant-onboarding/tenant-onboarding.zip"
  function_name    = "${var.project_name}-${var.environment}-tenant-onboarding"
  role             = aws_iam_role.lambda_execution.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 512
  source_code_hash = fileexists("${path.module}/../../../application/lambda-functions/tenant-onboarding/tenant-onboarding.zip") ? filebase64sha256("${path.module}/../../../application/lambda-functions/tenant-onboarding/tenant-onboarding.zip") : null

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      TENANTS_TABLE    = "${var.project_name}-tenants"
      DB_SECRET_ARN    = var.db_secret_arn
      TENANT_TIER      = var.tenant_tier
      USER_POOL_ID     = split("/", var.cognito_user_pool_arn)[1]
      ENVIRONMENT      = var.environment
    }
  }

  layers = [aws_lambda_layer_version.tenant_context.arn]

  tags = var.tags
}

# User Management Lambda
resource "aws_lambda_function" "user_management" {
  filename         = "${path.module}/../../../application/lambda-functions/user-management/user-management.zip"
  function_name    = "${var.project_name}-${var.environment}-user-management"
  role             = aws_iam_role.lambda_execution.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 512
  source_code_hash = fileexists("${path.module}/../../../application/lambda-functions/user-management/user-management.zip") ? filebase64sha256("${path.module}/../../../application/lambda-functions/user-management/user-management.zip") : null

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_NAME = var.db_secret_arn
      USER_POOL_ID   = split("/", var.cognito_user_pool_arn)[1]
      TENANT_TIER    = var.tenant_tier
    }
  }

  layers = [aws_lambda_layer_version.tenant_context.arn]

  tags = var.tags
}

# Product Service Lambda
resource "aws_lambda_function" "product_service" {
  filename         = "${path.module}/../../../application/lambda-functions/product-service/product-service.zip"
  function_name    = "${var.project_name}-${var.environment}-product-service"
  role             = aws_iam_role.lambda_execution.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 512
  source_code_hash = fileexists("${path.module}/../../../application/lambda-functions/product-service/product-service.zip") ? filebase64sha256("${path.module}/../../../application/lambda-functions/product-service/product-service.zip") : null

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_NAME = var.db_secret_arn
      TENANT_TIER    = var.tenant_tier
    }
  }

  layers = [aws_lambda_layer_version.tenant_context.arn]

  tags = var.tags
}

# Order Service Lambda
resource "aws_lambda_function" "order_service" {
  filename         = "${path.module}/../../../application/lambda-functions/order-service/order-service.zip"
  function_name    = "${var.project_name}-${var.environment}-order-service"
  role             = aws_iam_role.lambda_execution.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 512
  source_code_hash = fileexists("${path.module}/../../../application/lambda-functions/order-service/order-service.zip") ? filebase64sha256("${path.module}/../../../application/lambda-functions/order-service/order-service.zip") : null

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_NAME = var.db_secret_arn
      TENANT_TIER    = var.tenant_tier
    }
  }

  layers = [aws_lambda_layer_version.tenant_context.arn]

  tags = var.tags
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "lambda_logs" {
  for_each = toset([
    aws_lambda_function.tenant_onboarding.function_name,
    aws_lambda_function.user_management.function_name,
    aws_lambda_function.product_service.function_name,
    aws_lambda_function.order_service.function_name
  ])

  name              = "/aws/lambda/${each.value}"
  retention_in_days = 7

  tags = var.tags
}

# Outputs
output "lambda_role_arn" {
  description = "Lambda execution role ARN"
  value       = aws_iam_role.lambda_execution.arn
}

output "tenant_onboarding_arn" {
  description = "Tenant onboarding Lambda ARN"
  value       = aws_lambda_function.tenant_onboarding.arn
}

output "tenant_onboarding_invoke_arn" {
  description = "Tenant onboarding Lambda invoke ARN"
  value       = aws_lambda_function.tenant_onboarding.invoke_arn
}

output "user_management_arn" {
  description = "User management Lambda ARN"
  value       = aws_lambda_function.user_management.arn
}

output "user_management_invoke_arn" {
  description = "User management Lambda invoke ARN"
  value       = aws_lambda_function.user_management.invoke_arn
}

output "product_service_arn" {
  description = "Product service Lambda ARN"
  value       = aws_lambda_function.product_service.arn
}

output "product_service_invoke_arn" {
  description = "Product service Lambda invoke ARN"
  value       = aws_lambda_function.product_service.invoke_arn
}

output "order_service_arn" {
  description = "Order service Lambda ARN"
  value       = aws_lambda_function.order_service.arn
}

output "order_service_invoke_arn" {
  description = "Order service Lambda invoke ARN"
  value       = aws_lambda_function.order_service.invoke_arn
}

