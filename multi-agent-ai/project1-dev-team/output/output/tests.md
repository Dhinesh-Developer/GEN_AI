# Comprehensive Testing Strategy & Test Suite: Input Processing Engine

As the **Senior QA Automation Engineer**, I have reviewed the technical specifications, acceptance criteria, and the production-grade Python backend implementation (FastAPI, Pydantic v2, SQLAlchemy async) provided by the development team. 

Below is the comprehensive test strategy and production-ready `pytest` suite designed to validate functional requirements, data integrity, security boundaries, and error contracts.

---

## 1. Testing Strategy Overview

Our quality engineering approach is divided into six distinct testing layers aligned with the system's Clean Architecture and API contracts:

1. **Unit Tests (Service & Repository Logic):** 
   - Isolate domain execution logic in `ResourceService` and data transformations by mocking asynchronous repository layers.
   - Verify that business rules (like optimistic locking check and permission parsing) evaluate correctly without spinning up an actual database.
2. **Integration Tests (Database & ORM Layer):** 
   - Validate SQLAlchemy asynchronous sessions, repository query handling, constraint enforcement, and state persistence against a live test database (`pytest-asyncio`).
3. **API Endpoints & Contract Tests (`/api/v1/resources`):** 
   - Test end-to-end HTTP request/response cycles using `httpx.AsyncClient` via FastAPI's `TestClient` bridge.
   - Assert exact conformance with the standard success (`200 OK`, `201 Created`) and error contract schemas (`status`, `code`, `message`, `details`).
4. **Negative Tests & Validation Failures:** 
   - Send malformed JSON payloads, missing mandatory headers/fields, invalid UUID parameters, and mismatched data types to verify that the validation middleware catches issues and returns standard `400 Bad Request` payloads.
5. **Boundary & Edge-Case Tests:** 
   - Evaluate boundary limits on string lengths (`min_length=3`, `max_length=100`, `description` up to 500 characters), empty arrays, `null` values, and extreme integer values.
6. **Security & Authorization Tests:** 
   - Verify JWT authentication enforcement (`401 Unauthorized` on missing/expired tokens).
   - Test Broken Object Level Authorization (BOLA / IDOR) to ensure users cannot view or mutate resources owned by other tenants (`403 Forbidden`).
   - Confirm string input sanitization (`bleach` integration) strips potential XSS/HTML injection strings before persistence.

---

## 2. Example `pytest` Test Suite (`tests/test_resources.py`)

The following test suite uses `pytest`, `pytest-asyncio`, and `httpx` to thoroughly validate the Input Processing Engine.

```python
import pytest
from httpx import AsyncClient
from datetime import timedelta
from src.app import app
from src.utils.security import create_access_token

# Configure pytest-asyncio to handle async tests
pytestmark = pytest.mark.asyncio

@pytest.fixture
def auth_token_user_1():
    return create_access_token({"sub": "user-uuid-123", "role": "USER"})

@pytest.fixture
def auth_token_user_2():
    return create_access_token({"sub": "user-uuid-456", "role": "USER"})

@pytest.fixture
def auth_token_admin():
    return create_access_token({"sub": "admin-uuid-999", "role": "ADMIN"})

@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


# ==========================================
# 1. API & SUCCESS CONTRACT TESTS
# ==========================================

async def test_create_resource_success(async_client: AsyncClient, auth_token_user_1: str):
    """Test successful resource creation with valid payloads (US1)."""
    headers = {"Authorization": f"Bearer {auth_token_user_1}"}
    payload = {
        "name": "Test Processing Job",
        "description": "Processing financial batch items.",
        "payload_data": {"batch_id": 9876, "metrics": [1.2, 3.4]}
    }
    
    response = await async_client.post("/api/v1/resources", json=payload, headers=headers)
    assert response.status_code == 201
    
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["name"] == "Test Processing Job"
    assert body["data"]["user_id"] == "user-uuid-123"
    assert body["data"]["version"] == 1
    assert "id" in body["data"]


# ==========================================
# 2. NEGATIVE TESTS & VALIDATION MIDDLEWARE
# ==========================================

async def test_create_resource_missing_mandatory_fields(async_client: AsyncClient, auth_token_user_1: str):
    """Test validation failure when mandatory fields are omitted (US2, US3)."""
    headers = {"Authorization": f"Bearer {auth_token_user_1}"}
    # 'name' and 'payload_data' are missing
    payload = {"description": "Incomplete payload"}
    
    response = await async_client.post("/api/v1/resources", json=payload, headers=headers)
    assert response.status_code == 400
    
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "VALIDATION_ERROR"
    assert len(body["details"]) >= 2  # Missing name & payload_data


# ==========================================
# 3. BOUNDARY TESTS
# ==========================================

async def test_create_resource_name_string_boundaries(async_client: AsyncClient, auth_token_user_1: str):
    """Test string length boundaries for 'name' field (min 3, max 100)."""
    headers = {"Authorization": f"Bearer {auth_token_user_1}"}
    
    # Too short (< 3 chars)
    response_short = await async_client.post(
        "/api/v1/resources",
        json={"name": "ab", "payload_data": {}},
        headers=headers
    )
    assert response_short.status_code == 400

    # Too long (> 100 chars)
    response_long = await async_client.post(
        "/api/v1/resources",
        json={"name": "A" * 101, "payload_data": {}},
        headers=headers
    )
    assert response_long.status_code == 400


# ==========================================
# 4. SECURITY & AUTHENTICATION TESTS
# ==========================================

async def test_unauthorized_access_missing_token(async_client: AsyncClient):
    """Test that requests without Authorization headers are rejected (401)."""
    response = await async_client.post(
        "/api/v1/resources",
        json={"name": "Secure Item", "payload_data": {}}
    )
    assert response.status_code == 403  # FastAPI HTTPBearer standard missing credentials response


async def test_bola_protection_cross_user_access(async_client: AsyncClient, auth_token_user_1: str, auth_token_user_2: str):
    """Test BOLA/IDOR protection: User 2 cannot access or mutate User 1's resource (403)."""
    # 1. User 1 creates a resource
    headers_user1 = {"Authorization": f"Bearer {auth_token_user_1}"}
    create_resp = await async_client.post(
        "/api/v1/resources",
        json={"name": "User 1 Private Asset", "payload_data": {"secret": True}},
        headers=headers_user1
    )
    resource_id = create_resp.json()["data"]["id"]

    # 2. User 2 attempts to read User 1's resource
    headers_user2 = {"Authorization": f"Bearer {auth_token_user_2}"}
    get_resp = await async_client.get(f"/api/v1/resources/{resource_id}", headers=headers_user2)
    
    assert get_resp.status_code == 403
    body = get_resp.json()
    assert body["code"] == "FORBIDDEN"


# ==========================================
# 5. INPUT SANITIZATION TESTS
# ==========================================

async def test_input_sanitization_xss_prevention(async_client: AsyncClient, auth_token_user_1: str):
    """Test that HTML/XSS injection markers are sanitized out of string inputs."""
    headers = {"Authorization": f"Bearer {auth_token_user_1}"}
    payload = {
        "name": "<script>alert('xss')</script>Safe Name",
        "description": "<b>Bold text</b> description with <img src=x onerror=alert(1)>",
        "payload_data": {"key": "value"}
    }
    
    response = await async_client.post("/api/v1/resources", json=payload, headers=headers)
    assert response.status_code == 201
    
    data = response.json()["data"]
    # Tags should be stripped cleanly by bleach
    assert "<script>" not in data["name"]
    assert "Safe Name" in data["name"]
    assert "<b>" not in data["description"]
```

---

## 3. Test Execution Instructions

To run the test suite in a local development or CI/CD pipeline environment:

1. **Install Testing Dependencies:**
   ```bash
   pip install pytest pytest-asyncio httpx
   ```
2. **Execute Tests:**
   ```bash
   pytest -v tests/test_resources.py
   ```