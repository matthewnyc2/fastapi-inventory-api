"""FastAPI application entry point.

Configures middleware, mounts versioned routers, and creates database tables.
"""

import logging
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routes import auth, categories, inventory, orders, products

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

# ---------------------------------------------------------------------------
# Create tables
# ---------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "A production-style REST API for inventory management. "
        "Features JWT authentication with refresh tokens, full CRUD for "
        "products/categories/inventory/orders, pagination with filtering and sorting, "
        "an enforced order-status state machine, background low-stock alerts, "
        "and auto-generated OpenAPI documentation.\n\n"
        "**Authentication:** All write endpoints require a Bearer token obtained via "
        "`POST /api/v1/auth/login`. Read endpoints for products, categories, and "
        "inventory are public. Order endpoints require authentication for all operations."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "Health", "description": "Operational health check"},
        {"name": "Authentication", "description": "Register, login, and token refresh"},
        {"name": "Categories", "description": "Product category management (CRUD)"},
        {"name": "Products", "description": "Product catalog management (CRUD)"},
        {"name": "Inventory", "description": "Stock tracking, adjustments, and low-stock alerts"},
        {"name": "Orders", "description": "Order placement, status transitions, and cancellation"},
    ],
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request-ID middleware (production traceability)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Attach a unique X-Request-ID header to every response for tracing."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response: Response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(inventory.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get(
    "/health",
    tags=["Health"],
    summary="Health check endpoint",
    description="Returns service name, version, and status. Use for liveness probes.",
)
def health_check():
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "service": settings.APP_NAME,
    }
