"""Shared test fixtures for the Inventory Management API test suite.

Provides an isolated per-test SQLite database, a FastAPI TestClient with
dependency overrides, and helper functions for authentication and seeding.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# Test database (file-based SQLite, reset per test)
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite:///./test_inventory.db"

test_engine = create_engine(
    TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(test_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test, drop them after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client():
    """Provide a fresh TestClient for each test."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def registered_user(client):
    """Register a default test user and return the response data."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture()
def auth_token(client, registered_user):
    """Login the default test user and return the access token."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )
    return resp.json()["access_token"]


@pytest.fixture()
def auth_headers(auth_token):
    """Return Authorization headers dict for the default test user."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture()
def seeded_data(client, auth_headers):
    """Create a category, product, and inventory record. Return their IDs as a dict."""
    cat = client.post(
        "/api/v1/categories",
        json={"name": "Test Category", "description": "For testing"},
        headers=auth_headers,
    ).json()
    prod = client.post(
        "/api/v1/products",
        json={
            "sku": "TEST-001",
            "name": "Test Product",
            "description": "A test product",
            "price": 19.99,
            "category_id": cat["id"],
        },
        headers=auth_headers,
    ).json()
    inv = client.post(
        "/api/v1/inventory",
        json={
            "product_id": prod["id"],
            "quantity": 100,
            "low_stock_threshold": 10,
            "warehouse_location": "A1-01",
        },
        headers=auth_headers,
    ).json()
    return {"category_id": cat["id"], "product_id": prod["id"], "inventory_id": inv["id"]}
