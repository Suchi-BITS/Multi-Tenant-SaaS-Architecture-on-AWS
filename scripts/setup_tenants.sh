#!/bin/bash

# Setup Tenant Script
# Provisions a new tenant in the multi-tenant SaaS system

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Configuration
TENANT_NAME=""
TENANT_EMAIL=""
TENANT_TIER="pool"
API_URL=""

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Setup a new tenant in the multi-tenant SaaS system.

OPTIONS:
    --name NAME          Tenant company name (required)
    --email EMAIL        Admin email (required)
    --tier TIER          Tenant tier: pool, bridge, silo (default: pool)
    --api-url URL        API Gateway URL (required)
    -h, --help          Display this help

EXAMPLE:
    $0 --name "Acme Corp" --email admin@acme.com --tier pool --api-url https://api.example.com

EOF
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --name)
            TENANT_NAME="$2"
            shift 2
            ;;
        --email)
            TENANT_EMAIL="$2"
            shift 2
            ;;
        --tier)
            TENANT_TIER="$2"
            shift 2
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate parameters
if [ -z "$TENANT_NAME" ] || [ -z "$TENANT_EMAIL" ] || [ -z "$API_URL" ]; then
    echo "Error: Missing required parameters"
    usage
    exit 1
fi

print_info "Setting up tenant: $TENANT_NAME"
print_info "Email: $TENANT_EMAIL"
print_info "Tier: $TENANT_TIER"

# Call tenant onboarding API
print_info "Calling tenant onboarding API..."

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "${API_URL}/tenants" \
    -H "Content-Type: application/json" \
    -d "{
        \"company_name\": \"${TENANT_NAME}\",
        \"admin_email\": \"${TENANT_EMAIL}\",
        \"tier\": \"${TENANT_TIER}\"
    }")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" -eq 201 ]; then
    print_info "Tenant created successfully!"
    
    # Parse response
    TENANT_ID=$(echo "$BODY" | jq -r '.tenant_id')
    
    echo ""
    echo "==================== Tenant Details ===================="
    echo "Tenant ID: $TENANT_ID"
    echo "Company Name: $TENANT_NAME"
    echo "Admin Email: $TENANT_EMAIL"
    echo "Tier: $TENANT_TIER"
    echo "======================================================"
    echo ""
    
    print_info "Next steps:"
    echo "1. Admin user will receive an email with login credentials"
    echo "2. Login at: ${API_URL}/login"
    echo "3. Complete profile setup"
    
    # Save tenant info
    TENANT_FILE="tenant-${TENANT_ID}.json"
    echo "$BODY" | jq '.' > "$TENANT_FILE"
    print_info "Tenant details saved to: $TENANT_FILE"
    
else
    echo "Error: Tenant creation failed (HTTP $HTTP_CODE)"
    echo "$BODY" | jq '.' || echo "$BODY"
    exit 1
fi
