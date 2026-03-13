import importlib
import pytest
from fastapi.testclient import TestClient
import app.main


@pytest.fixture
def override_allowed_origins(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://example.com,https://another.com")
    importlib.reload(app.main)
    return app.main.app


def test_cors_middleware_allowed_origin(override_allowed_origins):
    client = TestClient(override_allowed_origins)

    # Test an allowed origin
    response = client.options(
        "/health",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://example.com"


def test_cors_middleware_disallowed_origin(override_allowed_origins):
    client = TestClient(override_allowed_origins)

    # Test a disallowed origin
    response = client.options(
        "/health",
        headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_middleware_fallback(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    importlib.reload(app.main)
    client = TestClient(app.main.app)

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )
