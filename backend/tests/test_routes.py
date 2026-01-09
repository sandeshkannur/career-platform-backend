# backend/tests/test_routes.py

import pytest

# NOTE:
# These tests are intentionally lightweight "smoke tests" to confirm routes exist.
# We do NOT try to validate full auth behavior here because:
# - Some endpoints are public (e.g., GET /v1/career-clusters)
# - Some endpoints are POST-only (e.g., admin upload endpoints), so GET returns 405 by design
#
# This keeps the test stable while still catching accidental route removals.

@pytest.mark.parametrize(
    "route, expected_statuses",
    [
        # Public endpoints (should be reachable without auth)
        ("/", (200,)),
        ("/v1/career-clusters", (200,)),
        ("/v1/questions", (200, 401, 403)),

        # Collection endpoints that exist but may require a specific HTTP method or auth
        # /v1/assessments is mounted as /v1/assessments/ in the app, so we use the exact path.
        ("/v1/assessments/", (401, 403, 422, 405)),  # depending on method/auth implementation

        # POST-only endpoints: GET should return 405 (route exists but method not allowed)
        ("/v1/admin/upload-careers", (405,)),
    ],
)
def test_api_routes_exist(client, route, expected_statuses):
    response = client.get(route)
    assert (
        response.status_code in expected_statuses
    ), f"{route}: expected one of {expected_statuses}, got {response.status_code} ({response.text})"
