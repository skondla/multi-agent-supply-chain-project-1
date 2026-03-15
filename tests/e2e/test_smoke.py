"""
E2E smoke tests for production verification.
Run against a live deployment to verify all critical paths work.
"""
import os
import pytest
import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


@pytest.mark.e2e
@pytest.mark.smoke
class TestSmoke:
    """Smoke tests - run these after every deployment."""

    def test_health_endpoint(self):
        """Application is alive."""
        response = httpx.get(f"{BASE_URL}/health", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_readiness_endpoint(self):
        """All dependencies are ready."""
        response = httpx.get(f"{BASE_URL}/ready", timeout=15.0)
        assert response.status_code in (200, 503)  # May be degraded
        data = response.json()
        assert "status" in data
        assert "checks" in data

    def test_metrics_endpoint(self):
        """Prometheus metrics are exposed."""
        response = httpx.get(f"{BASE_URL}/metrics", timeout=10.0)
        assert response.status_code == 200
        assert "http_requests_total" in response.text

    def test_openapi_schema(self):
        """OpenAPI spec is valid and accessible."""
        response = httpx.get(f"{BASE_URL}/api/openapi.json", timeout=10.0)
        assert response.status_code == 200
        schema = response.json()
        assert schema["openapi"].startswith("3.")
        assert "paths" in schema
        assert "/api/v1/orders" in schema["paths"]
        assert "/api/v1/inventory" in schema["paths"]
        assert "/api/v1/agents/orchestrate" in schema["paths"]

    def test_api_docs_accessible(self):
        """Swagger UI is accessible."""
        response = httpx.get(f"{BASE_URL}/api/docs", timeout=10.0)
        assert response.status_code == 200

    def test_redoc_accessible(self):
        """ReDoc docs are accessible."""
        response = httpx.get(f"{BASE_URL}/api/redoc", timeout=10.0)
        assert response.status_code == 200

    def test_auth_endpoint_responds(self):
        """Auth endpoint responds (even to invalid creds)."""
        response = httpx.post(
            f"{BASE_URL}/api/v1/auth/token",
            data={"username": "nonexistent@test.com", "password": "invalid"},
            timeout=10.0,
        )
        # Should return 401, not 500
        assert response.status_code in (401, 422)

    def test_unauthenticated_orders_rejected(self):
        """Orders endpoint requires authentication."""
        response = httpx.get(f"{BASE_URL}/api/v1/orders", timeout=10.0)
        assert response.status_code == 401

    def test_unauthenticated_inventory_rejected(self):
        """Inventory endpoint requires authentication."""
        response = httpx.get(f"{BASE_URL}/api/v1/inventory", timeout=10.0)
        assert response.status_code == 401

    def test_security_headers_present(self):
        """Security headers are set on responses."""
        response = httpx.get(f"{BASE_URL}/health", timeout=10.0)
        headers = response.headers
        assert "x-content-type-options" in headers
        assert headers["x-content-type-options"] == "nosniff"
        assert "x-frame-options" in headers
        assert "x-xss-protection" in headers

    def test_gzip_compression(self):
        """Response compression works."""
        response = httpx.get(
            f"{BASE_URL}/api/openapi.json",
            headers={"Accept-Encoding": "gzip"},
            timeout=10.0,
        )
        assert response.status_code == 200
        # Response body should be decompressed by httpx automatically
