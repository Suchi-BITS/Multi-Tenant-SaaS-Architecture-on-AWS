# Bridge Model Environment Configuration

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
    key            = "bridge/terraform.tfstate"
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

variable "tenant_id" {
  description = "Tenant ID (required for bridge model)"
  type        = string
}

# Bridge-specific configuration
locals {
  project_name = "multitenant-saas"
  tenant_tier  = "bridge"
  
  bridge_config = {
    vpc_cidr             = "10.1.0.0/16"
    db_instance_class    = "db.t3.small"
    db_allocated_storage = 50
    lambda_memory        = 1024
    lambda_timeout       = 60
    max_tenants          = 500
  }
  
  tags = {
    Project     = local.project_name
    Environment = var.environment
    TenantTier  = local.tenant_tier
    TenantId    = var.tenant_id
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
  vpc_cidr       = local.bridge_config.vpc_cidr
  
  database_instance_class = {
    pool   = "db.t3.micro"
    bridge = local.bridge_config.db_instance_class
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

output "tenant_schema_name" {
  description = "Tenant Schema Name"
  value       = "tenant_${replace(var.tenant_id, "-", "_")}"
}
