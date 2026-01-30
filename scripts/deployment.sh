#!/bin/bash

################################################################################
# AWS Serverless SaaS Application Deployment Script
#
# This script deploys the complete multi-tenant SaaS infrastructure including:
# - DynamoDB tables
# - Lambda functions
# - API Gateway
# - Cognito User Pool
# - CloudWatch monitoring
#
# Usage: ./deploy.sh [environment] [isolation-model]
#   environment: dev, staging, or prod (default: dev)
#   isolation-model: pool or silo (default: pool)
################################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT=${1:-dev}
ISOLATION_MODEL=${2:-pool}
STACK_NAME="serverless-saas-${ENVIRONMENT}"
REGION=${AWS_REGION:-us-east-1}
S3_BUCKET="serverless-saas-deploy-${ENVIRONMENT}-$(date +%s)"

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}AWS Serverless SaaS Deployment${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "Environment:      ${YELLOW}${ENVIRONMENT}${NC}"
echo -e "Isolation Model:  ${YELLOW}${ISOLATION_MODEL}${NC}"
echo -e "Stack Name:       ${YELLOW}${STACK_NAME}${NC}"
echo -e "Region:           ${YELLOW}${REGION}${NC}"
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Check SAM CLI
if ! command -v sam &> /dev/null; then
    echo -e "${RED}Error: AWS SAM CLI is not installed${NC}"
    exit 1
fi

# Validate AWS credentials
echo -e "${GREEN}Validating AWS credentials...${NC}"
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: Invalid AWS credentials${NC}"
    exit 1
fi
echo -e "${GREEN}✓ AWS credentials validated${NC}"
echo ""

# Create S3 bucket for deployment artifacts
echo -e "${GREEN}Creating S3 bucket for deployment...${NC}"
aws s3 mb s3://${S3_BUCKET} --region ${REGION} 2>/dev/null || true
echo -e "${GREEN}✓ S3 bucket ready${NC}"
echo ""

# Install Python dependencies
echo -e "${GREEN}Installing Python dependencies...${NC}"
cd server/shared
pip install -r requirements.txt -t . 2>/dev/null || true
cd ../..
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Build SAM application
echo -e "${GREEN}Building SAM application...${NC}"
sam build \
    --template-file infrastructure/sam/template.yaml \
    --use-container \
    --region ${REGION}
echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Deploy SAM application
echo -e "${GREEN}Deploying SAM application...${NC}"
sam deploy \
    --template-file .aws-sam/build/template.yaml \
    --stack-name ${STACK_NAME} \
    --s3-bucket ${S3_BUCKET} \
    --parameter-overrides \
        Environment=${ENVIRONMENT} \
        IsolationModel=${ISOLATION_MODEL} \
    --capabilities CAPABILITY_IAM \
    --region ${REGION} \
    --no-fail-on-empty-changeset \
    --no-confirm-changeset

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Deployment complete${NC}"
else
    echo -e "${RED}✗ Deployment failed${NC}"
    exit 1
fi
echo ""

# Get stack outputs
echo -e "${GREEN}Retrieving stack outputs...${NC}"
API_URL=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
    --output text)

USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
    --output text)

CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
    --output text)

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Deployment Summary${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "API URL:          ${YELLOW}${API_URL}${NC}"
echo -e "User Pool ID:     ${YELLOW}${USER_POOL_ID}${NC}"
echo -e "Client ID:        ${YELLOW}${CLIENT_ID}${NC}"
echo ""

# Create .env file for frontend
echo -e "${GREEN}Creating environment file for frontend...${NC}"
cat > client/.env << EOF
REACT_APP_API_URL=${API_URL}
REACT_APP_USER_POOL_ID=${USER_POOL_ID}
REACT_APP_CLIENT_ID=${CLIENT_ID}
REACT_APP_REGION=${REGION}
EOF
echo -e "${GREEN}✓ Environment file created at client/.env${NC}"
echo ""

# Display next steps
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Next Steps${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "1. Deploy the frontend application:"
echo "   cd client"
echo "   npm install"
echo "   npm start"
echo ""
echo "2. Register a new tenant:"
echo "   curl -X POST ${API_URL}/tenants \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"company_name\":\"Acme Corp\",\"admin_email\":\"admin@acme.com\",\"tier\":\"basic\"}'"
echo ""
echo "3. Monitor your application:"
echo "   aws cloudwatch get-dashboard --dashboard-name ${STACK_NAME}-dashboard"
echo ""
echo -e "${GREEN}Deployment completed successfully!${NC}"
