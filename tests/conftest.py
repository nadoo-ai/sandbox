"""
Pytest configuration and fixtures for Nadoo Sandbox tests
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_key():
    """Test API key"""
    return "test-api-key-12345"


@pytest.fixture
def client():
    """FastAPI test client"""
    from src.main import app

    return TestClient(app)


@pytest.fixture
def auth_headers(api_key):
    """Authentication headers for API requests"""
    return {"X-API-Key": api_key}
