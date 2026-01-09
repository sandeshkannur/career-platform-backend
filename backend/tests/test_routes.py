import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root_works():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()

@pytest.mark.parametrize("route", [
    "/v1/assessments",
    "/v1/admin/upload-careers",
    "/v1/students",
    "/v1/skills",
    "/v1/career-clusters",
])
def test_api_routes_exist(route):
    response = client.get(route)
    assert response.status_code in (401, 403, 422), f"Expected auth error, got {response.status_code}"
