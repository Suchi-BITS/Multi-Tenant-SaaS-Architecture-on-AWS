# Pool Model Environment Configuration

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "terraform-state-multitenant-saas"
    key            = "pool/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = var.aws_region
}

# Variables
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "admin_email" {
  description = "Admin email"
  type        = string
}

# Pool-specific configuration
locals {
  project_name = "multitenant-saas"
  tenant_tier  = "pool"
  
  pool_config = {
    vpc_cidr             = "10.0.0.0/16"
    db_instance_class    = "db.t3.micro"
    db_allocated_storage = 20
    lambda_memory        = 512
    lambda_timeout       = 30
    max_tenants          = 1000
  }
  
  tags = {
    Project     = local.project_name
    Environment = var.environment
    TenantTier  = local.tenant_tier
    ManagedBy   = "Terraform"
  }
}

# Use root module
module "infrastructure" {
  source = "../../"

  aws_region     = var.aws_region
  environment    = var.environment
  tenant_tier    = local.tenant_tier
  admin_email    = var.admin_email
  vpc_cidr       = local.pool_config.vpc_cidr
  
  database_instance_class = {
    pool   = local.pool_config.db_instance_class
    bridge = "db.t3.small"
    silo   = "db.t3.medium"
  }
}

# Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.infrastructure.vpc_id
}

output "api_gateway_url" {
  description = "API Gateway URL"
  value       = module.infrastructure.api_gateway_url
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.infrastructure.cognito_user_pool_id
}

output "cognito_client_id" {
  description = "Cognito Client ID"
  value       = module.infrastructure.cognito_client_id
}

output "dynamodb_table_name" {
  description = "DynamoDB Table Name"
  value       = module.infrastructure.dynamodb_table_name
}
