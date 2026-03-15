"""
Load testing with Locust.
Run: locust -f tests/load/locustfile.py --host=http://localhost:8000
"""
import json
import random
import string
from locust import HttpUser, task, between, events


def random_sku() -> str:
    return f"SKU-{random.randint(1, 500):03d}"


def random_customer_id() -> str:
    return f"CUST-{random.randint(1, 1000):04d}"


class SupplyChainUser(HttpUser):
    """Simulates a supply chain platform user."""
    wait_time = between(0.5, 2.0)
    token: str = ""

    def on_start(self):
        """Authenticate on start."""
        response = self.client.post(
            "/api/v1/auth/token",
            data={"username": "loadtest@example.com", "password": "LoadTest123!"},
            name="/auth/token",
        )
        if response.status_code == 200:
            self.token = response.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(35)
    def list_orders(self):
        """Most common: browse orders list."""
        page = random.randint(1, 5)
        self.client.get(
            f"/api/v1/orders?page={page}&size=20",
            headers=self.headers,
            name="/orders (list)",
        )

    @task(20)
    def create_order(self):
        """Create a new order."""
        order_data = {
            "customer_id": random_customer_id(),
            "items": [
                {
                    "sku": random_sku(),
                    "quantity": random.randint(1, 20),
                    "unit_price": round(random.uniform(5.0, 500.0), 2),
                }
                for _ in range(random.randint(1, 5))
            ],
            "shipping_address": {
                "street": "123 Load Test Ave",
                "city": "Test City",
                "state": "CA",
                "zip": "90210",
                "country": "US",
            },
            "priority": random.choice(["low", "medium", "high"]),
        }
        self.client.post(
            "/api/v1/orders",
            json=order_data,
            headers=self.headers,
            name="/orders (create)",
        )

    @task(25)
    def check_inventory(self):
        """Check inventory levels."""
        sku = random_sku()
        self.client.get(
            f"/api/v1/inventory/{sku}",
            headers=self.headers,
            name="/inventory/{sku}",
        )

    @task(10)
    def list_inventory(self):
        """Browse inventory."""
        self.client.get(
            "/api/v1/inventory?page=1&size=20",
            headers=self.headers,
            name="/inventory (list)",
        )

    @task(5)
    def check_agents_status(self):
        """Monitor agent health."""
        self.client.get(
            "/api/v1/agents/status",
            headers=self.headers,
            name="/agents/status",
        )

    @task(3)
    def get_analytics_dashboard(self):
        """Load dashboard data."""
        self.client.get(
            "/api/v1/analytics/dashboard",
            headers=self.headers,
            name="/analytics/dashboard",
        )

    @task(2)
    def health_check(self):
        """Health probe."""
        self.client.get("/health", name="/health")


class AnalystUser(HttpUser):
    """Simulates a supply chain analyst focused on reports."""
    wait_time = between(2.0, 5.0)
    token: str = ""

    def on_start(self):
        response = self.client.post(
            "/api/v1/auth/token",
            data={"username": "analyst@example.com", "password": "Analyst123!"},
        )
        if response.status_code == 200:
            self.token = response.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(40)
    def get_analytics(self):
        self.client.get("/api/v1/analytics/dashboard", headers=self.headers)

    @task(30)
    def get_supplier_performance(self):
        self.client.get("/api/v1/analytics/supplier-performance", headers=self.headers)

    @task(20)
    def get_demand_forecast(self):
        sku = random_sku()
        self.client.get(
            f"/api/v1/analytics/demand-forecast?sku={sku}&horizon_days=30",
            headers=self.headers,
            name="/analytics/demand-forecast",
        )

    @task(10)
    def get_inventory_turnover(self):
        self.client.get("/api/v1/analytics/inventory-turnover", headers=self.headers)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print(f"\n{'='*60}")
    print("Supply Chain AI Platform - Load Test Starting")
    print(f"Target: {environment.host}")
    print(f"{'='*60}\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print(f"\n{'='*60}")
    print("Load Test Complete")
    stats = environment.stats.total
    print(f"Total Requests: {stats.num_requests}")
    print(f"Failures: {stats.num_failures}")
    print(f"Avg Response Time: {stats.avg_response_time:.1f}ms")
    print(f"P95 Response Time: {stats.get_response_time_percentile(0.95):.1f}ms")
    print(f"P99 Response Time: {stats.get_response_time_percentile(0.99):.1f}ms")
    print(f"RPS: {stats.current_rps:.1f}")
    print(f"{'='*60}\n")
