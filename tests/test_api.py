"""Comprehensive test suite for the Inventory Management API.

Covers happy paths, edge cases, error states, auth failures, validation
boundaries, and the order status state machine. Each test is isolated
via the autouse setup_database fixture in conftest.py.
"""

import pytest


# ===========================================================================
# Health
# ===========================================================================

class TestHealth:
    def test_health_check_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "service" in data

    def test_health_check_includes_request_id(self, client):
        resp = client.get("/health")
        assert "x-request-id" in resp.headers

    def test_health_check_echoes_custom_request_id(self, client):
        resp = client.get("/health", headers={"X-Request-ID": "custom-123"})
        assert resp.headers["x-request-id"] == "custom-123"


# ===========================================================================
# Authentication
# ===========================================================================

class TestRegister:
    def test_register_success(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "new@example.com",
                "password": "password123",
                "full_name": "New User",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["email"] == "new@example.com"
        assert data["full_name"] == "New User"
        assert data["is_active"] is True
        assert data["is_admin"] is False
        assert "hashed_password" not in data
        assert "id" in data
        assert "created_at" in data

    def test_register_without_full_name(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "noname", "email": "no@name.com", "password": "password123"},
        )
        assert resp.status_code == 201
        assert resp.json()["full_name"] is None

    def test_register_duplicate_email(self, client, registered_user):
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "other", "email": "test@example.com", "password": "password123"},
        )
        assert resp.status_code == 409
        assert "email" in resp.json()["detail"].lower()

    def test_register_duplicate_username(self, client, registered_user):
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "testuser", "email": "other@example.com", "password": "password123"},
        )
        assert resp.status_code == 409
        assert "username" in resp.json()["detail"].lower()

    def test_register_password_too_short(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "short", "email": "s@s.com", "password": "1234567"},
        )
        assert resp.status_code == 422

    def test_register_username_too_short(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "ab", "email": "ab@ab.com", "password": "password123"},
        )
        assert resp.status_code == 422

    def test_register_missing_required_fields(self, client):
        resp = client.post("/api/v1/auth/register", json={})
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client, registered_user):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "testpass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, registered_user):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "ghost", "password": "password123"},
        )
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422


class TestTokenRefresh:
    def test_refresh_success(self, client, registered_user):
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "testuser", "password": "testpass123"},
        )
        refresh = login_resp.json()["refresh_token"]
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_with_access_token_rejected(self, client, auth_token):
        """Using an access token in place of a refresh token should fail."""
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": auth_token})
        assert resp.status_code == 401

    def test_refresh_with_garbage_token(self, client):
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "not.a.token"})
        assert resp.status_code == 401

    def test_refresh_missing_field(self, client):
        resp = client.post("/api/v1/auth/refresh", json={})
        assert resp.status_code == 422


class TestAuthProtection:
    def test_protected_route_without_token(self, client):
        resp = client.post("/api/v1/categories", json={"name": "Fail"})
        assert resp.status_code == 403

    def test_protected_route_with_invalid_token(self, client):
        resp = client.post(
            "/api/v1/categories",
            json={"name": "Fail"},
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_protected_route_with_malformed_header(self, client):
        resp = client.post(
            "/api/v1/categories",
            json={"name": "Fail"},
            headers={"Authorization": "NotBearer token"},
        )
        assert resp.status_code == 403


# ===========================================================================
# Categories
# ===========================================================================

class TestCategoryCreate:
    def test_create_category(self, client, auth_headers):
        resp = client.post(
            "/api/v1/categories",
            json={"name": "Electronics", "description": "Gadgets and devices"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Electronics"
        assert data["description"] == "Gadgets and devices"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_category_without_description(self, client, auth_headers):
        resp = client.post(
            "/api/v1/categories",
            json={"name": "Bare"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["description"] is None

    def test_create_duplicate_name_rejected(self, client, auth_headers):
        client.post("/api/v1/categories", json={"name": "Dup"}, headers=auth_headers)
        resp = client.post("/api/v1/categories", json={"name": "Dup"}, headers=auth_headers)
        assert resp.status_code == 409

    def test_create_empty_name_rejected(self, client, auth_headers):
        resp = client.post("/api/v1/categories", json={"name": ""}, headers=auth_headers)
        assert resp.status_code == 422


class TestCategoryRead:
    def test_get_single_category(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Tools"}, headers=auth_headers
        ).json()
        resp = client.get(f"/api/v1/categories/{cat['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Tools"

    def test_get_nonexistent_category(self, client):
        resp = client.get("/api/v1/categories/99999")
        assert resp.status_code == 404

    def test_list_categories_empty(self, client):
        resp = client.get("/api/v1/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["total_pages"] == 0

    def test_list_with_pagination(self, client, auth_headers):
        for i in range(5):
            client.post(
                "/api/v1/categories",
                json={"name": f"Category {i}"},
                headers=auth_headers,
            )
        resp = client.get("/api/v1/categories?page=1&page_size=2")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["total_pages"] == 3

    def test_list_page_beyond_range(self, client, auth_headers):
        client.post("/api/v1/categories", json={"name": "Solo"}, headers=auth_headers)
        resp = client.get("/api/v1/categories?page=999")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_search_categories(self, client, auth_headers):
        client.post("/api/v1/categories", json={"name": "Electronics"}, headers=auth_headers)
        client.post("/api/v1/categories", json={"name": "Furniture"}, headers=auth_headers)
        resp = client.get("/api/v1/categories?search=elec")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["name"] == "Electronics"

    def test_sort_categories_desc(self, client, auth_headers):
        client.post("/api/v1/categories", json={"name": "Alpha"}, headers=auth_headers)
        client.post("/api/v1/categories", json={"name": "Zeta"}, headers=auth_headers)
        resp = client.get("/api/v1/categories?sort_by=name&sort_order=desc")
        items = resp.json()["items"]
        assert items[0]["name"] == "Zeta"
        assert items[1]["name"] == "Alpha"


class TestCategoryUpdate:
    def test_update_category(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Old Name"}, headers=auth_headers
        ).json()
        resp = client.put(
            f"/api/v1/categories/{cat['id']}",
            json={"name": "New Name"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_update_nonexistent(self, client, auth_headers):
        resp = client.put(
            "/api/v1/categories/99999",
            json={"name": "Ghost"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_update_name_conflict(self, client, auth_headers):
        client.post("/api/v1/categories", json={"name": "A"}, headers=auth_headers)
        cat_b = client.post(
            "/api/v1/categories", json={"name": "B"}, headers=auth_headers
        ).json()
        resp = client.put(
            f"/api/v1/categories/{cat_b['id']}",
            json={"name": "A"},
            headers=auth_headers,
        )
        assert resp.status_code == 409


class TestCategoryDelete:
    def test_delete_category(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Delete Me"}, headers=auth_headers
        ).json()
        resp = client.delete(f"/api/v1/categories/{cat['id']}", headers=auth_headers)
        assert resp.status_code == 204
        resp = client.get(f"/api/v1/categories/{cat['id']}")
        assert resp.status_code == 404

    def test_delete_nonexistent(self, client, auth_headers):
        resp = client.delete("/api/v1/categories/99999", headers=auth_headers)
        assert resp.status_code == 404


# ===========================================================================
# Products
# ===========================================================================

class TestProductCreate:
    def test_create_product(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        resp = client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-001",
                "name": "Widget",
                "description": "A fine widget",
                "price": 9.99,
                "category_id": cat["id"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["sku"] == "SKU-001"
        assert data["name"] == "Widget"
        assert data["price"] == 9.99
        assert data["category"] is not None
        assert data["category"]["name"] == "Cat"

    def test_create_product_nonexistent_category(self, client, auth_headers):
        resp = client.post(
            "/api/v1/products",
            json={"sku": "SKU-X", "name": "Bad", "price": 1.0, "category_id": 99999},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_create_duplicate_sku_rejected(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        client.post(
            "/api/v1/products",
            json={"sku": "DUP-001", "name": "A", "price": 1.0, "category_id": cat["id"]},
            headers=auth_headers,
        )
        resp = client.post(
            "/api/v1/products",
            json={"sku": "DUP-001", "name": "B", "price": 2.0, "category_id": cat["id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    def test_create_product_zero_price_rejected(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        resp = client.post(
            "/api/v1/products",
            json={"sku": "FREE-001", "name": "Free", "price": 0, "category_id": cat["id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_product_negative_price_rejected(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        resp = client.post(
            "/api/v1/products",
            json={"sku": "NEG-001", "name": "Neg", "price": -5.0, "category_id": cat["id"]},
            headers=auth_headers,
        )
        assert resp.status_code == 422


class TestProductRead:
    def test_get_product_with_category(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        prod = client.post(
            "/api/v1/products",
            json={"sku": "SKU-001", "name": "Widget", "price": 9.99, "category_id": cat["id"]},
            headers=auth_headers,
        ).json()
        resp = client.get(f"/api/v1/products/{prod['id']}")
        assert resp.status_code == 200
        assert resp.json()["category"]["name"] == "Cat"

    def test_get_nonexistent_product(self, client):
        resp = client.get("/api/v1/products/99999")
        assert resp.status_code == 404

    def test_list_products_empty(self, client):
        resp = client.get("/api/v1/products")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_products_price_range_filter(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        for i, price in enumerate([5.0, 15.0, 25.0, 35.0]):
            client.post(
                "/api/v1/products",
                json={"sku": f"P-{i}", "name": f"P{i}", "price": price, "category_id": cat["id"]},
                headers=auth_headers,
            )
        resp = client.get("/api/v1/products?min_price=10&max_price=30")
        assert resp.json()["total"] == 2

    def test_list_products_category_filter(self, client, auth_headers):
        cat1 = client.post(
            "/api/v1/categories", json={"name": "Cat1"}, headers=auth_headers
        ).json()
        cat2 = client.post(
            "/api/v1/categories", json={"name": "Cat2"}, headers=auth_headers
        ).json()
        client.post(
            "/api/v1/products",
            json={"sku": "C1-001", "name": "In Cat1", "price": 1.0, "category_id": cat1["id"]},
            headers=auth_headers,
        )
        client.post(
            "/api/v1/products",
            json={"sku": "C2-001", "name": "In Cat2", "price": 1.0, "category_id": cat2["id"]},
            headers=auth_headers,
        )
        resp = client.get(f"/api/v1/products?category_id={cat1['id']}")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["sku"] == "C1-001"

    def test_list_products_search_by_sku(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        client.post(
            "/api/v1/products",
            json={"sku": "ELEC-001", "name": "Mouse", "price": 1.0, "category_id": cat["id"]},
            headers=auth_headers,
        )
        resp = client.get("/api/v1/products?search=ELEC")
        assert resp.json()["total"] == 1

    def test_sort_products_by_price_desc(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        client.post(
            "/api/v1/products",
            json={"sku": "A-001", "name": "Cheap", "price": 5.0, "category_id": cat["id"]},
            headers=auth_headers,
        )
        client.post(
            "/api/v1/products",
            json={"sku": "B-001", "name": "Expensive", "price": 99.0, "category_id": cat["id"]},
            headers=auth_headers,
        )
        resp = client.get("/api/v1/products?sort_by=price&sort_order=desc")
        items = resp.json()["items"]
        assert items[0]["price"] >= items[1]["price"]


class TestProductUpdate:
    def test_update_product(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        prod = client.post(
            "/api/v1/products",
            json={"sku": "SKU-001", "name": "Old", "price": 10.0, "category_id": cat["id"]},
            headers=auth_headers,
        ).json()
        resp = client.put(
            f"/api/v1/products/{prod['id']}",
            json={"name": "New", "price": 20.0},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"
        assert resp.json()["price"] == 20.0

    def test_update_product_nonexistent(self, client, auth_headers):
        resp = client.put(
            "/api/v1/products/99999",
            json={"name": "Ghost"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_update_product_sku_conflict(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        client.post(
            "/api/v1/products",
            json={"sku": "A-001", "name": "A", "price": 1.0, "category_id": cat["id"]},
            headers=auth_headers,
        )
        prod_b = client.post(
            "/api/v1/products",
            json={"sku": "B-001", "name": "B", "price": 1.0, "category_id": cat["id"]},
            headers=auth_headers,
        ).json()
        resp = client.put(
            f"/api/v1/products/{prod_b['id']}",
            json={"sku": "A-001"},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    def test_update_product_invalid_category(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        prod = client.post(
            "/api/v1/products",
            json={"sku": "SKU-001", "name": "P", "price": 1.0, "category_id": cat["id"]},
            headers=auth_headers,
        ).json()
        resp = client.put(
            f"/api/v1/products/{prod['id']}",
            json={"category_id": 99999},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestProductDelete:
    def test_delete_product(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        prod = client.post(
            "/api/v1/products",
            json={"sku": "DEL-001", "name": "Del", "price": 1.0, "category_id": cat["id"]},
            headers=auth_headers,
        ).json()
        resp = client.delete(f"/api/v1/products/{prod['id']}", headers=auth_headers)
        assert resp.status_code == 204
        assert client.get(f"/api/v1/products/{prod['id']}").status_code == 404

    def test_delete_nonexistent_product(self, client, auth_headers):
        resp = client.delete("/api/v1/products/99999", headers=auth_headers)
        assert resp.status_code == 404


# ===========================================================================
# Inventory
# ===========================================================================

class TestInventoryCreate:
    def test_create_inventory(self, client, auth_headers, seeded_data):
        # seeded_data already created one; create a second product
        cat_id = seeded_data["category_id"]
        prod = client.post(
            "/api/v1/products",
            json={"sku": "NEW-001", "name": "New", "price": 5.0, "category_id": cat_id},
            headers=auth_headers,
        ).json()
        resp = client.post(
            "/api/v1/inventory",
            json={"product_id": prod["id"], "quantity": 50, "low_stock_threshold": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["quantity"] == 50
        assert data["is_low_stock"] is False
        assert data["last_restocked"] is not None

    def test_create_inventory_zero_quantity(self, client, auth_headers):
        cat = client.post(
            "/api/v1/categories", json={"name": "Cat"}, headers=auth_headers
        ).json()
        prod = client.post(
            "/api/v1/products",
            json={"sku": "ZERO-001", "name": "Zero", "price": 1.0, "category_id": cat["id"]},
            headers=auth_headers,
        ).json()
        resp = client.post(
            "/api/v1/inventory",
            json={"product_id": prod["id"], "quantity": 0},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["last_restocked"] is None

    def test_create_duplicate_inventory_rejected(self, client, auth_headers, seeded_data):
        resp = client.post(
            "/api/v1/inventory",
            json={"product_id": seeded_data["product_id"], "quantity": 10},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    def test_create_inventory_nonexistent_product(self, client, auth_headers):
        resp = client.post(
            "/api/v1/inventory",
            json={"product_id": 99999, "quantity": 10},
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestInventoryAdjust:
    def test_adjust_down(self, client, auth_headers, seeded_data):
        inv_id = seeded_data["inventory_id"]
        resp = client.post(
            f"/api/v1/inventory/{inv_id}/adjust",
            json={"adjustment": -20, "reason": "Sold"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["quantity"] == 80

    def test_adjust_up_sets_restocked(self, client, auth_headers, seeded_data):
        inv_id = seeded_data["inventory_id"]
        resp = client.post(
            f"/api/v1/inventory/{inv_id}/adjust",
            json={"adjustment": 50, "reason": "Restocked"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["quantity"] == 150
        assert resp.json()["last_restocked"] is not None

    def test_adjust_to_exact_zero(self, client, auth_headers, seeded_data):
        inv_id = seeded_data["inventory_id"]
        resp = client.post(
            f"/api/v1/inventory/{inv_id}/adjust",
            json={"adjustment": -100, "reason": "Cleared out"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["quantity"] == 0

    def test_adjust_below_zero_rejected(self, client, auth_headers, seeded_data):
        inv_id = seeded_data["inventory_id"]
        resp = client.post(
            f"/api/v1/inventory/{inv_id}/adjust",
            json={"adjustment": -101, "reason": "Over-sell"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "insufficient" in resp.json()["detail"].lower()

    def test_adjust_nonexistent_inventory(self, client, auth_headers):
        resp = client.post(
            "/api/v1/inventory/99999/adjust",
            json={"adjustment": 1, "reason": "Test"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_adjust_missing_reason_rejected(self, client, auth_headers, seeded_data):
        inv_id = seeded_data["inventory_id"]
        resp = client.post(
            f"/api/v1/inventory/{inv_id}/adjust",
            json={"adjustment": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 422


class TestInventoryRead:
    def test_get_single_inventory(self, client, seeded_data):
        resp = client.get(f"/api/v1/inventory/{seeded_data['inventory_id']}")
        assert resp.status_code == 200
        assert resp.json()["quantity"] == 100

    def test_get_nonexistent_inventory(self, client):
        resp = client.get("/api/v1/inventory/99999")
        assert resp.status_code == 404

    def test_list_inventory(self, client, seeded_data):
        resp = client.get("/api/v1/inventory")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_low_stock_filter(self, client, auth_headers, seeded_data):
        inv_id = seeded_data["inventory_id"]
        # Deplete below threshold (100 - 95 = 5, threshold is 10)
        client.post(
            f"/api/v1/inventory/{inv_id}/adjust",
            json={"adjustment": -95, "reason": "Sale"},
            headers=auth_headers,
        )
        resp = client.get("/api/v1/inventory?low_stock_only=true")
        assert resp.json()["total"] == 1

    def test_low_stock_alerts_endpoint(self, client, auth_headers, seeded_data):
        inv_id = seeded_data["inventory_id"]
        client.post(
            f"/api/v1/inventory/{inv_id}/adjust",
            json={"adjustment": -95, "reason": "Sale"},
            headers=auth_headers,
        )
        resp = client.get("/api/v1/inventory/low-stock")
        assert resp.status_code == 200
        alerts = resp.json()
        assert len(alerts) == 1
        assert alerts[0]["current_quantity"] == 5
        assert alerts[0]["sku"] == "TEST-001"

    def test_low_stock_alerts_empty_when_stocked(self, client, seeded_data):
        resp = client.get("/api/v1/inventory/low-stock")
        assert resp.status_code == 200
        assert resp.json() == []


class TestInventoryUpdate:
    def test_update_inventory(self, client, auth_headers, seeded_data):
        inv_id = seeded_data["inventory_id"]
        resp = client.put(
            f"/api/v1/inventory/{inv_id}",
            json={"low_stock_threshold": 25, "warehouse_location": "B2-05"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["low_stock_threshold"] == 25
        assert data["warehouse_location"] == "B2-05"

    def test_update_nonexistent_inventory(self, client, auth_headers):
        resp = client.put(
            "/api/v1/inventory/99999",
            json={"quantity": 10},
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ===========================================================================
# Orders
# ===========================================================================

class TestOrderCreate:
    def test_create_order(self, client, auth_headers, seeded_data):
        resp = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Jane Doe",
                "customer_email": "jane@example.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 2}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["total_amount"] == pytest.approx(39.98)
        assert len(data["items"]) == 1
        assert data["items"][0]["unit_price"] == 19.99
        assert data["order_number"].startswith("ORD-")

    def test_create_order_deducts_inventory(self, client, auth_headers, seeded_data):
        client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 10}],
            },
            headers=auth_headers,
        )
        inv = client.get(f"/api/v1/inventory/{seeded_data['inventory_id']}").json()
        assert inv["quantity"] == 90

    def test_create_order_insufficient_stock(self, client, auth_headers, seeded_data):
        resp = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 999}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "insufficient" in resp.json()["detail"].lower()

    def test_create_order_nonexistent_product(self, client, auth_headers):
        resp = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": 99999, "quantity": 1}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_create_order_empty_items_rejected(self, client, auth_headers):
        resp = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_order_zero_quantity_rejected(self, client, auth_headers, seeded_data):
        resp = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 0}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_create_order_with_notes(self, client, auth_headers, seeded_data):
        resp = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "notes": "Rush delivery please",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 1}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["notes"] == "Rush delivery please"

    def test_create_order_requires_auth(self, client, seeded_data):
        resp = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 1}],
            },
        )
        assert resp.status_code == 403


class TestOrderRead:
    def test_get_order(self, client, auth_headers, seeded_data):
        order = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 1}],
            },
            headers=auth_headers,
        ).json()
        resp = client.get(f"/api/v1/orders/{order['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["order_number"] == order["order_number"]

    def test_get_nonexistent_order(self, client, auth_headers):
        resp = client.get("/api/v1/orders/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_list_orders(self, client, auth_headers, seeded_data):
        client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 1}],
            },
            headers=auth_headers,
        )
        resp = client.get("/api/v1/orders", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_orders_requires_auth(self, client):
        resp = client.get("/api/v1/orders")
        assert resp.status_code == 403

    def test_list_orders_filter_by_status(self, client, auth_headers, seeded_data):
        order = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 1}],
            },
            headers=auth_headers,
        ).json()
        # Confirm the order
        client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "confirmed"},
            headers=auth_headers,
        )
        resp = client.get("/api/v1/orders?status=confirmed", headers=auth_headers)
        assert resp.json()["total"] == 1
        resp_pending = client.get("/api/v1/orders?status=pending", headers=auth_headers)
        assert resp_pending.json()["total"] == 0

    def test_list_orders_filter_by_email(self, client, auth_headers, seeded_data):
        client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Unique",
                "customer_email": "unique@specific.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 1}],
            },
            headers=auth_headers,
        )
        resp = client.get(
            "/api/v1/orders?customer_email=unique@specific",
            headers=auth_headers,
        )
        assert resp.json()["total"] == 1


class TestOrderStatusTransitions:
    """Test the full order status state machine."""

    def _create_order(self, client, auth_headers, product_id, qty=1):
        return client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": product_id, "quantity": qty}],
            },
            headers=auth_headers,
        ).json()

    def test_full_lifecycle_pending_to_delivered(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        oid = order["id"]

        for target in ["confirmed", "shipped", "delivered"]:
            resp = client.patch(
                f"/api/v1/orders/{oid}/status",
                json={"status": target},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == target

    def test_pending_to_cancelled(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        resp = client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "cancelled"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_confirmed_to_cancelled(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "confirmed"},
            headers=auth_headers,
        )
        resp = client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "cancelled"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_invalid_transition_pending_to_shipped(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        resp = client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "shipped"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_invalid_transition_pending_to_delivered(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        resp = client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "delivered"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_invalid_transition_shipped_to_cancelled(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        oid = order["id"]
        client.patch(f"/api/v1/orders/{oid}/status", json={"status": "confirmed"}, headers=auth_headers)
        client.patch(f"/api/v1/orders/{oid}/status", json={"status": "shipped"}, headers=auth_headers)
        resp = client.patch(
            f"/api/v1/orders/{oid}/status",
            json={"status": "cancelled"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_delivered_is_terminal(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        oid = order["id"]
        for s in ["confirmed", "shipped", "delivered"]:
            client.patch(f"/api/v1/orders/{oid}/status", json={"status": s}, headers=auth_headers)
        for s in ["pending", "confirmed", "shipped", "cancelled"]:
            resp = client.patch(
                f"/api/v1/orders/{oid}/status", json={"status": s}, headers=auth_headers
            )
            assert resp.status_code == 400

    def test_cancelled_is_terminal(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "cancelled"},
            headers=auth_headers,
        )
        for s in ["pending", "confirmed", "shipped", "delivered"]:
            resp = client.patch(
                f"/api/v1/orders/{order['id']}/status",
                json={"status": s},
                headers=auth_headers,
            )
            assert resp.status_code == 400

    def test_cancel_restores_inventory(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"], qty=10)
        inv_before = client.get(f"/api/v1/inventory/{seeded_data['inventory_id']}").json()
        assert inv_before["quantity"] == 90

        client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "cancelled"},
            headers=auth_headers,
        )
        inv_after = client.get(f"/api/v1/inventory/{seeded_data['inventory_id']}").json()
        assert inv_after["quantity"] == 100

    def test_update_status_nonexistent_order(self, client, auth_headers):
        resp = client.patch(
            "/api/v1/orders/99999/status",
            json={"status": "confirmed"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_update_status_invalid_value(self, client, auth_headers, seeded_data):
        order = self._create_order(client, auth_headers, seeded_data["product_id"])
        resp = client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "bogus"},
            headers=auth_headers,
        )
        assert resp.status_code == 422


class TestOrderDelete:
    def test_delete_pending_order(self, client, auth_headers, seeded_data):
        order = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 5}],
            },
            headers=auth_headers,
        ).json()
        resp = client.delete(f"/api/v1/orders/{order['id']}", headers=auth_headers)
        assert resp.status_code == 204

    def test_delete_pending_order_restores_inventory(self, client, auth_headers, seeded_data):
        order = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 10}],
            },
            headers=auth_headers,
        ).json()
        client.delete(f"/api/v1/orders/{order['id']}", headers=auth_headers)
        inv = client.get(f"/api/v1/inventory/{seeded_data['inventory_id']}").json()
        assert inv["quantity"] == 100

    def test_delete_confirmed_order_rejected(self, client, auth_headers, seeded_data):
        order = client.post(
            "/api/v1/orders",
            json={
                "customer_name": "Test",
                "customer_email": "t@t.com",
                "items": [{"product_id": seeded_data["product_id"], "quantity": 1}],
            },
            headers=auth_headers,
        ).json()
        client.patch(
            f"/api/v1/orders/{order['id']}/status",
            json={"status": "confirmed"},
            headers=auth_headers,
        )
        resp = client.delete(f"/api/v1/orders/{order['id']}", headers=auth_headers)
        assert resp.status_code == 400

    def test_delete_nonexistent_order(self, client, auth_headers):
        resp = client.delete("/api/v1/orders/99999", headers=auth_headers)
        assert resp.status_code == 404
