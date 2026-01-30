"""
Integration Tests for Multi-Tenant SaaS
Tests tenant isolation and API functionality
"""

import pytest
import requests
import json
import uuid
from typing import Dict

# Test configuration
API_BASE_URL = "https://api.example.com/v1"
TEST_TENANT_A = "tenant-a"
TEST_TENANT_B = "tenant-b"

class TestTenantIsolation:
    """Test tenant data isolation"""
    
    @pytest.fixture
    def tenant_a_token(self):
        """Get JWT token for tenant A"""
        # In real tests, authenticate and get token
        return "eyJ..."  # Mock token
    
    @pytest.fixture
    def tenant_b_token(self):
        """Get JWT token for tenant B"""
        return "eyJ..."  # Mock token
    
    def test_create_user_tenant_a(self, tenant_a_token):
        """Test creating user in tenant A"""
        response = requests.post(
            f"{API_BASE_URL}/users",
            headers={"Authorization": f"Bearer {tenant_a_token}"},
            json={
                "email": "user@tenanta.com",
                "name": "User A",
                "password": "SecurePass123!"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "user_id" in data["user"]
        
        return data["user"]["user_id"]
    
    def test_list_users_tenant_a(self, tenant_a_token):
        """Test listing users for tenant A"""
        response = requests.get(
            f"{API_BASE_URL}/users",
            headers={"Authorization": f"Bearer {tenant_a_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        
        # Verify all users belong to tenant A
        for user in data["users"]:
            # Tenant ID should be in token, not visible in response
            assert "email" in user
    
    def test_tenant_isolation(self, tenant_a_token, tenant_b_token):
        """Test that tenant B cannot access tenant A's data"""
        # Create user in tenant A
        response_a = requests.post(
            f"{API_BASE_URL}/users",
            headers={"Authorization": f"Bearer {tenant_a_token}"},
            json={
                "email": "isolated@tenanta.com",
                "name": "Isolated User",
                "password": "SecurePass123!"
            }
        )
        
        assert response_a.status_code == 201
        user_id = response_a.json()["user"]["user_id"]
        
        # Try to access tenant A's user from tenant B
        response_b = requests.get(
            f"{API_BASE_URL}/users/{user_id}",
            headers={"Authorization": f"Bearer {tenant_b_token}"}
        )
        
        # Should return 404 (not found) or 403 (forbidden)
        assert response_b.status_code in [403, 404]


class TestAPIFunctionality:
    """Test API endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        return "eyJ..."  # Mock token
    
    def test_create_product(self, auth_token):
        """Test creating a product"""
        response = requests.post(
            f"{API_BASE_URL}/products",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": "Test Product",
                "description": "Test description",
                "price": 99.99,
                "stock_quantity": 100
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Product created"
        assert "product_id" in data["product"]
    
    def test_list_products(self, auth_token):
        """Test listing products"""
        response = requests.get(
            f"{API_BASE_URL}/products?limit=10",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert isinstance(data["products"], list)
    
    def test_create_order(self, auth_token):
        """Test creating an order"""
        # First create a product
        product_response = requests.post(
            f"{API_BASE_URL}/products",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": "Order Test Product",
                "price": 50.00,
                "stock_quantity": 10
            }
        )
        product_id = product_response.json()["product"]["product_id"]
        
        # Create a user
        user_response = requests.post(
            f"{API_BASE_URL}/users",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "email": "orderuser@test.com",
                "name": "Order User",
                "password": "SecurePass123!"
            }
        )
        user_id = user_response.json()["user"]["user_id"]
        
        # Create order
        order_response = requests.post(
            f"{API_BASE_URL}/orders",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "user_id": user_id,
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 2,
                        "unit_price": 50.00
                    }
                ],
                "shipping_address": {
                    "street": "123 Main St",
                    "city": "San Francisco",
                    "state": "CA",
                    "zip": "94105"
                }
            }
        )
        
        assert order_response.status_code == 201
        data = order_response.json()
        assert "order_id" in data["order"]
        assert data["order"]["total_amount"] > 100  # With tax and shipping


class TestTenantOnboarding:
    """Test tenant onboarding process"""
    
    def test_onboard_tenant(self):
        """Test tenant onboarding"""
        response = requests.post(
            f"{API_BASE_URL}/tenants",
            json={
                "company_name": f"Test Company {uuid.uuid4().hex[:8]}",
                "admin_email": f"admin-{uuid.uuid4().hex[:8]}@test.com",
                "tier": "pool"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "tenant_id" in data
        assert "admin_user" in data
    
    def test_onboard_tenant_duplicate_email(self):
        """Test onboarding with duplicate email"""
        email = f"duplicate-{uuid.uuid4().hex[:8]}@test.com"
        
        # First onboarding
        response1 = requests.post(
            f"{API_BASE_URL}/tenants",
            json={
                "company_name": "Test Company 1",
                "admin_email": email,
                "tier": "pool"
            }
        )
        assert response1.status_code == 201
        
        # Duplicate onboarding
        response2 = requests.post(
            f"{API_BASE_URL}/tenants",
            json={
                "company_name": "Test Company 2",
                "admin_email": email,
                "tier": "pool"
            }
        )
        assert response2.status_code == 409  # Conflict


class TestPerformance:
    """Performance and load tests"""
    
    @pytest.fixture
    def auth_token(self):
        return "eyJ..."  # Mock token
    
    def test_api_response_time(self, auth_token):
        """Test API response time"""
        import time
        
        start = time.time()
        response = requests.get(
            f"{API_BASE_URL}/products?limit=10",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        duration = (time.time() - start) * 1000
        
        assert response.status_code == 200
        assert duration < 1000  # Less than 1 second
    
    def test_concurrent_requests(self, auth_token):
        """Test concurrent requests"""
        import concurrent.futures
        
        def make_request():
            response = requests.get(
                f"{API_BASE_URL}/products",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            return response.status_code == 200
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(100)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        success_rate = sum(results) / len(results) * 100
        assert success_rate >= 95  # At least 95% success rate


class TestErrorHandling:
    """Test error handling"""
    
    def test_unauthorized_request(self):
        """Test request without authentication"""
        response = requests.get(f"{API_BASE_URL}/users")
        assert response.status_code == 401
    
    def test_invalid_token(self):
        """Test request with invalid token"""
        response = requests.get(
            f"{API_BASE_URL}/users",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401
    
    def test_not_found(self, auth_token="eyJ..."):
        """Test accessing non-existent resource"""
        response = requests.get(
            f"{API_BASE_URL}/users/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 404
    
    def test_invalid_input(self, auth_token="eyJ..."):
        """Test with invalid input data"""
        response = requests.post(
            f"{API_BASE_URL}/users",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "email": "invalid-email",  # Invalid email format
                "name": "Test User"
                # Missing password
            }
        )
        assert response.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
