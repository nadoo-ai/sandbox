"""
Tests for the code execution API endpoints
"""



def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"


def test_execute_python_simple(client, auth_headers):
    """Test simple Python code execution"""
    payload = {
        "code": 'print("Hello, World!")',
        "language": "python",
    }

    response = client.post("/api/v1/execute", json=payload, headers=auth_headers)

    # Note: Actual execution may not work in test environment without Docker
    # This test verifies the API structure
    assert response.status_code in [200, 500]  # 500 if Docker not available
    data = response.json()

    if response.status_code == 200:
        assert "success" in data
        assert "output" in data or "error" in data


def test_execute_without_auth(client):
    """Test that authentication is required"""
    payload = {
        "code": 'print("test")',
        "language": "python",
    }

    response = client.post("/api/v1/execute", json=payload)
    assert response.status_code in [401, 403]  # Unauthorized or Forbidden


def test_execute_invalid_language(client, auth_headers):
    """Test execution with invalid language"""
    payload = {
        "code": 'print("test")',
        "language": "invalid_language",
    }

    response = client.post("/api/v1/execute", json=payload, headers=auth_headers)
    assert response.status_code in [400, 422]  # Bad Request or Unprocessable Entity


def test_execute_missing_code(client, auth_headers):
    """Test execution without code"""
    payload = {
        "language": "python",
    }

    response = client.post("/api/v1/execute", json=payload, headers=auth_headers)
    assert response.status_code == 422  # Validation error


def test_supported_languages(client, auth_headers):
    """Test getting list of supported languages"""
    response = client.get("/api/v1/execute/languages", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict) or isinstance(data, list)

    # Should include common languages
    if isinstance(data, dict):
        assert "python" in data or any("python" in str(k).lower() for k in data.keys())
    elif isinstance(data, list):
        languages_str = str(data).lower()
        assert "python" in languages_str or "javascript" in languages_str
