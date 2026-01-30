# Silo Model Environment Configuration

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
    key            = "silo/terraform.tfstate"
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
  default     = "prod"
}

variable "admin_email" {
  description = "Admin email"
  type        = string
}

variable "tenant_id" {
  description = "Tenant ID (required for silo model)"
  type        = string
}

variable "tenant_name" {
  description = "Tenant name"
  type        = string
}

# Silo-specific configuration
locals {
  project_name = "multitenant-saas"
  tenant_tier  = "silo"
  
  silo_config = {
    vpc_cidr             = "10.2.0.0/16"
    db_instance_class    = "db.r5.large"
    db_allocated_storage = 100
    lambda_memory        = 2048
    lambda_timeout       = 60
    multi_az             = true
  }
  
  tags = {
    Project     = local.project_name
    Environment = var.environment
    TenantTier  = local.tenant_tier
    TenantId    = var.tenant_id
    TenantName  = var.tenant_name
    ManagedBy   = "Terraform"
  }
}

# Use root module
module "infrastructure" {
  source = "../../"

  aws_region     = var.aws_region
  environment    = var.environment
  tenant_tier    = local.tenant_tier
  tenant_id      = var.tenant_id
  admin_email    = var.admin_email
  vpc_cidr       = local.silo_config.vpc_cidr
  
  database_instance_class = {
    pool   = "db.t3.micro"
    bridge = "db.t3.small"
    silo   = local.silo_config.db_instance_class
  }
}

# Dedicated resources for silo tenant
resource "aws_kms_key" "tenant" {
  description             = "KMS key for ${var.tenant_name}"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = local.tags
}

resource "aws_kms_alias" "tenant" {
  name          = "alias/${var.tenant_id}"
  target_key_id = aws_kms_key.tenant.key_id
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

output "dedicated_database_endpoint" {
  description = "Dedicated Database Endpoint"
  value       = "Dedicated RDS instance for tenant ${var.tenant_id}"
}

output "kms_key_id" {
  description = "KMS Key ID"
  value       = aws_kms_key.tenant.key_id
}
