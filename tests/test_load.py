"""
Load Testing Script for Multi-Tenant SaaS
Uses Locust for load testing
"""

from locust import HttpUser, task, between
import random
import json

class MultiTenantSaaSUser(HttpUser):
    """Simulated user for load testing"""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Called when a user starts"""
        # Authenticate and get token
        self.token = self.authenticate()
    
    def authenticate(self):
        """Authenticate and get JWT token"""
        # In real tests, authenticate with Cognito
        # For now, use a test token
        return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    
    @task(3)
    def list_products(self):
        """List products - most common operation"""
        self.client.get(
            "/products",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/products [LIST]"
        )
    
    @task(2)
    def get_product(self):
        """Get specific product"""
        product_id = random.choice(self.product_ids) if hasattr(self, 'product_ids') else "test-id"
        self.client.get(
            f"/products/{product_id}",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/products/:id [GET]"
        )
    
    @task(1)
    def create_product(self):
        """Create new product"""
        response = self.client.post(
            "/products",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            json={
                "name": f"Product {random.randint(1000, 9999)}",
                "description": "Load test product",
                "price": round(random.uniform(10, 1000), 2),
                "stock_quantity": random.randint(1, 100),
                "category": random.choice(["electronics", "clothing", "books"])
            },
            name="/products [CREATE]"
        )
        
        if response.status_code == 201:
            data = response.json()
            if hasattr(self, 'product_ids'):
                self.product_ids.append(data["product"]["product_id"])
            else:
                self.product_ids = [data["product"]["product_id"]]
    
    @task(2)
    def list_users(self):
        """List users"""
        self.client.get(
            "/users",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/users [LIST]"
        )
    
    @task(1)
    def create_user(self):
        """Create new user"""
        user_num = random.randint(10000, 99999)
        self.client.post(
            "/users",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            json={
                "email": f"loadtest{user_num}@example.com",
                "name": f"Load Test User {user_num}",
                "password": "LoadTest123!",
                "role": "user"
            },
            name="/users [CREATE]"
        )
    
    @task(1)
    def create_order(self):
        """Create new order"""
        if not hasattr(self, 'product_ids') or not self.product_ids:
            return
        
        self.client.post(
            "/orders",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            json={
                "user_id": "test-user-id",
                "items": [
                    {
                        "product_id": random.choice(self.product_ids),
                        "quantity": random.randint(1, 5),
                        "unit_price": round(random.uniform(10, 100), 2)
                    }
                ],
                "shipping_address": {
                    "street": "123 Test St",
                    "city": "Test City",
                    "state": "TS",
                    "zip": "12345"
                }
            },
            name="/orders [CREATE]"
        )


class TenantAUser(MultiTenantSaaSUser):
    """User from Tenant A"""
    
    def authenticate(self):
        """Get Tenant A token"""
        return "tenant_a_token"


class TenantBUser(MultiTenantSaaSUser):
    """User from Tenant B"""
    
    def authenticate(self):
        """Get Tenant B token"""
        return "tenant_b_token"


# Locust configuration
# Run with: locust -f load_test.py --host=https://api.example.com/v1

# Example commands:
# locust -f load_test.py --host=https://api.example.com/v1 --users 100 --spawn-rate 10
# locust -f load_test.py --headless --users 1000 --spawn-rate 50 --run-time 10m


"""
Load Test Scenarios:

1. Smoke Test (Minimal Load):
   - Users: 10
   - Duration: 2 minutes
   - Purpose: Verify basic functionality

2. Load Test (Normal Load):
   - Users: 100
   - Duration: 10 minutes
   - Purpose: Test under expected load

3. Stress Test (High Load):
   - Users: 500-1000
   - Duration: 15 minutes
   - Purpose: Find breaking points

4. Spike Test (Sudden Load):
   - Start: 10 users
   - Spike to: 500 users in 1 minute
   - Duration: 10 minutes
   - Purpose: Test auto-scaling

5. Endurance Test (Sustained Load):
   - Users: 200
   - Duration: 2 hours
   - Purpose: Test memory leaks, resource exhaustion
"""


# Custom load shapes
from locust import LoadTestShape

class StepLoadShape(LoadTestShape):
    """
    Step load pattern:
    - Start with 10 users
    - Every minute, add 50 users
    - Up to 500 users
    """
    
    step_time = 60  # 1 minute
    step_load = 50
    spawn_rate = 10
    max_users = 500
    
    def tick(self):
        run_time = self.get_run_time()
        
        if run_time > 600:  # 10 minutes
            return None
        
        current_step = run_time // self.step_time
        user_count = min(10 + (current_step * self.step_load), self.max_users)
        
        return (user_count, self.spawn_rate)


class SpikeLoadShape(LoadTestShape):
    """
    Spike load pattern:
    - Normal: 50 users
    - Spike: 500 users for 2 minutes
    - Back to normal
    """
    
    def tick(self):
        run_time = self.get_run_time()
        
        if run_time < 300:  # First 5 minutes
            return (50, 10)
        elif run_time < 420:  # Spike for 2 minutes
            return (500, 50)
        elif run_time < 600:  # Cool down
            return (50, 10)
        else:
            return None


# Performance metrics to track:
# - Response time (p50, p95, p99)
# - Requests per second
# - Error rate
# - Resource utilization (CPU, Memory)
# - Database connections
# - Lambda cold starts
