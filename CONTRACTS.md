# API Contracts

Every endpoint in this API is defined by a contract with five fields:
**Input**, **Output**, **Precondition**, **Postcondition**, and **Side Effects**.

---

## Data Dictionary

### User
| Property | Type | Constraints |
|---|---|---|
| id | int | PK, auto-increment |
| email | str(255) | unique, not null |
| username | str(100) | unique, not null, pattern `^[a-zA-Z0-9_-]+$` |
| hashed_password | str(255) | not null, bcrypt hash |
| full_name | str(255) | nullable |
| is_active | bool | default true |
| is_admin | bool | default false |
| created_at | datetime | auto-set UTC |

### Category
| Property | Type | Constraints |
|---|---|---|
| id | int | PK, auto-increment |
| name | str(100) | unique, not null |
| description | text | nullable |
| created_at | datetime | auto-set UTC |
| updated_at | datetime | auto-set UTC, auto-update |

### Product
| Property | Type | Constraints |
|---|---|---|
| id | int | PK, auto-increment |
| sku | str(50) | unique, not null, pattern `^[A-Z0-9]+-[A-Z0-9]+$` |
| name | str(200) | not null |
| description | text | nullable |
| price | float | > 0, <= 999999.99 |
| category_id | int | FK -> categories.id, not null |
| created_at | datetime | auto-set UTC |
| updated_at | datetime | auto-set UTC, auto-update |

### Inventory
| Property | Type | Constraints |
|---|---|---|
| id | int | PK, auto-increment |
| product_id | int | FK -> products.id, unique, not null |
| quantity | int | >= 0, not null |
| low_stock_threshold | int | >= 0, default 10 |
| warehouse_location | str(100) | nullable |
| last_restocked | datetime | nullable, set on positive adjustment |
| updated_at | datetime | auto-set UTC, auto-update |

**Computed:** `is_low_stock = quantity <= low_stock_threshold`

### Order
| Property | Type | Constraints |
|---|---|---|
| id | int | PK, auto-increment |
| order_number | str(50) | unique, auto-generated `ORD-{hex8}` |
| customer_name | str(200) | not null |
| customer_email | str(255) | not null |
| status | str(20) | enum: pending, confirmed, shipped, delivered, cancelled |
| notes | text | nullable |
| total_amount | float | sum of line-item subtotals |
| created_at | datetime | auto-set UTC |
| updated_at | datetime | auto-set UTC, auto-update |

**Status Transitions:**
```
pending  -> confirmed | cancelled
confirmed -> shipped  | cancelled
shipped  -> delivered
delivered -> (terminal)
cancelled -> (terminal)
```

### OrderItem
| Property | Type | Constraints |
|---|---|---|
| id | int | PK, auto-increment |
| order_id | int | FK -> orders.id, not null |
| product_id | int | FK -> products.id, not null |
| quantity | int | > 0 |
| unit_price | float | captured at order time |
| subtotal | float | quantity * unit_price |

---

## Endpoint Contracts

### POST /api/v1/auth/register
- **Input:** `{email, username, password, full_name?}`
- **Output:** `UserResponse` (201)
- **Precondition:** email not in users table; username not in users table
- **Postcondition:** new row in users with hashed password
- **Side Effects:** none

### POST /api/v1/auth/login
- **Input:** `{username, password}`
- **Output:** `Token {access_token, refresh_token, token_type}` (200)
- **Precondition:** user exists, password matches hash, user is active
- **Postcondition:** JWT pair issued with user ID as subject
- **Side Effects:** none

### POST /api/v1/auth/refresh
- **Input:** `{refresh_token}`
- **Output:** `Token` (200)
- **Precondition:** token is valid JWT, type is "refresh", user exists and is active
- **Postcondition:** new JWT pair issued
- **Side Effects:** none

### GET /api/v1/categories
- **Input:** query params `{page, page_size, search?, sort_by, sort_order}`
- **Output:** `PaginatedResponse[CategoryResponse]` (200)
- **Precondition:** none
- **Postcondition:** result set matches filters
- **Side Effects:** none

### GET /api/v1/categories/{id}
- **Input:** path param `category_id`
- **Output:** `CategoryResponse` (200) or 404
- **Precondition:** category with id exists
- **Postcondition:** none
- **Side Effects:** none

### POST /api/v1/categories
- **Input:** `{name, description?}` + Bearer token
- **Output:** `CategoryResponse` (201)
- **Precondition:** authenticated; name not in categories table
- **Postcondition:** new row in categories
- **Side Effects:** none

### PUT /api/v1/categories/{id}
- **Input:** `{name?, description?}` + Bearer token + path param
- **Output:** `CategoryResponse` (200) or 404/409
- **Precondition:** authenticated; category exists; new name (if provided) is unique
- **Postcondition:** row updated
- **Side Effects:** none

### DELETE /api/v1/categories/{id}
- **Input:** path param + Bearer token
- **Output:** 204 or 404
- **Precondition:** authenticated; category exists
- **Postcondition:** row deleted
- **Side Effects:** none

### GET /api/v1/products
- **Input:** query params `{page, page_size, search?, category_id?, min_price?, max_price?, sort_by, sort_order}`
- **Output:** `PaginatedResponse[ProductResponse]` (200)
- **Precondition:** none
- **Postcondition:** result set matches filters; category eager-loaded
- **Side Effects:** none

### GET /api/v1/products/{id}
- **Input:** path param `product_id`
- **Output:** `ProductResponse` (200) or 404
- **Precondition:** product exists
- **Postcondition:** category relationship loaded
- **Side Effects:** none

### POST /api/v1/products
- **Input:** `{sku, name, description?, price, category_id}` + Bearer token
- **Output:** `ProductResponse` (201) or 404/409
- **Precondition:** authenticated; category_id FK valid; sku unique
- **Postcondition:** new row in products
- **Side Effects:** none

### PUT /api/v1/products/{id}
- **Input:** partial `{sku?, name?, description?, price?, category_id?}` + Bearer token
- **Output:** `ProductResponse` (200) or 404/409
- **Precondition:** authenticated; product exists; new sku unique; new category_id valid
- **Postcondition:** row updated
- **Side Effects:** none

### DELETE /api/v1/products/{id}
- **Input:** path param + Bearer token
- **Output:** 204 or 404
- **Precondition:** authenticated; product exists
- **Postcondition:** row deleted
- **Side Effects:** none

### GET /api/v1/inventory
- **Input:** query params `{page, page_size, low_stock_only?, sort_by, sort_order}`
- **Output:** `PaginatedResponse[InventoryResponse]` (200)
- **Precondition:** none
- **Postcondition:** is_low_stock computed for each record
- **Side Effects:** none

### GET /api/v1/inventory/low-stock
- **Input:** none
- **Output:** `list[LowStockAlert]` (200)
- **Precondition:** none
- **Postcondition:** all records where quantity <= threshold returned
- **Side Effects:** none

### GET /api/v1/inventory/{id}
- **Input:** path param `inventory_id`
- **Output:** `InventoryResponse` (200) or 404
- **Precondition:** inventory record exists
- **Postcondition:** is_low_stock computed
- **Side Effects:** none

### POST /api/v1/inventory
- **Input:** `{product_id, quantity, low_stock_threshold?, warehouse_location?}` + Bearer token
- **Output:** `InventoryResponse` (201) or 404/409
- **Precondition:** authenticated; product exists; no existing inventory for product
- **Postcondition:** new row; last_restocked set if quantity > 0
- **Side Effects:** none

### PUT /api/v1/inventory/{id}
- **Input:** partial `{quantity?, low_stock_threshold?, warehouse_location?}` + Bearer token
- **Output:** `InventoryResponse` (200) or 404
- **Precondition:** authenticated; inventory record exists
- **Postcondition:** row updated
- **Side Effects:** none

### POST /api/v1/inventory/{id}/adjust
- **Input:** `{adjustment, reason}` + Bearer token
- **Output:** `InventoryResponse` (200) or 400/404
- **Precondition:** authenticated; inventory record exists; quantity + adjustment >= 0
- **Postcondition:** quantity updated; last_restocked set if adjustment > 0
- **Side Effects:** background task checks low-stock alert

### GET /api/v1/orders
- **Input:** query params `{page, page_size, status?, customer_email?, sort_by, sort_order}` + Bearer token
- **Output:** `PaginatedResponse[OrderResponse]` (200)
- **Precondition:** authenticated
- **Postcondition:** items eager-loaded
- **Side Effects:** none

### GET /api/v1/orders/{id}
- **Input:** path param + Bearer token
- **Output:** `OrderResponse` (200) or 404
- **Precondition:** authenticated; order exists
- **Postcondition:** items eager-loaded
- **Side Effects:** none

### POST /api/v1/orders
- **Input:** `{customer_name, customer_email, notes?, items[{product_id, quantity}]}` + Bearer token
- **Output:** `OrderResponse` (201) or 400/404
- **Precondition:** authenticated; all products exist; sufficient inventory for each line
- **Postcondition:** order created with status "pending"; inventory deducted for each line
- **Side Effects:** inventory.quantity decreased for each line item

### PATCH /api/v1/orders/{id}/status
- **Input:** `{status}` + Bearer token
- **Output:** `OrderResponse` (200) or 400/404
- **Precondition:** authenticated; order exists; transition is valid per state machine
- **Postcondition:** status updated; inventory restored if cancelled
- **Side Effects:** inventory.quantity restored for each line item on cancellation

### DELETE /api/v1/orders/{id}
- **Input:** path param + Bearer token
- **Output:** 204 or 400/404
- **Precondition:** authenticated; order exists; status is "pending"
- **Postcondition:** order and items deleted; inventory restored
- **Side Effects:** inventory.quantity restored for each line item
