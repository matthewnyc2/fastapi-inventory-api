"""CRUD routes for inventory management.

Contract:
  Input:  InventoryCreate | InventoryUpdate | InventoryAdjust payloads; path param inventory_id.
  Output: InventoryResponse (single) | PaginatedResponse[InventoryResponse] (list) |
          list[LowStockAlert] (low-stock endpoint).
  Precondition: product_id FK valid; one inventory record per product; quantity >= 0 after adjust.
  Postcondition: row created/updated in inventory table; background low-stock check on adjust.
  Side effects: background task logs warning when stock <= threshold.
"""

import logging
import math
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.inventory import (
    InventoryAdjust,
    InventoryCreate,
    InventoryResponse,
    InventoryUpdate,
    LowStockAlert,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


# ---------------------------------------------------------------------------
# Background task: low-stock alert check
# ---------------------------------------------------------------------------

def check_low_stock_alerts(product_id: int, db_url: str):
    """Background task that logs a warning when stock drops below threshold."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SA_Session

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    with SA_Session(engine) as session:
        inv = (
            session.query(Inventory)
            .options(joinedload(Inventory.product))
            .filter(Inventory.product_id == product_id)
            .first()
        )
        if inv and inv.quantity <= inv.low_stock_threshold:
            logger.warning(
                "LOW STOCK ALERT: Product '%s' (SKU: %s) has %d units remaining "
                "(threshold: %d)",
                inv.product.name,
                inv.product.sku,
                inv.quantity,
                inv.low_stock_threshold,
            )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _enrich(inv: Inventory) -> dict:
    """Add computed is_low_stock field."""
    data = {
        "id": inv.id,
        "product_id": inv.product_id,
        "quantity": inv.quantity,
        "low_stock_threshold": inv.low_stock_threshold,
        "warehouse_location": inv.warehouse_location,
        "last_restocked": inv.last_restocked,
        "updated_at": inv.updated_at,
        "is_low_stock": inv.quantity <= inv.low_stock_threshold,
    }
    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=PaginatedResponse[InventoryResponse],
    summary="List inventory records with pagination",
    description="Returns paginated inventory records with a computed is_low_stock flag. "
    "Use low_stock_only=true to filter to items at or below their threshold.",
)
def list_inventory(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    low_stock_only: bool = Query(False, description="Show only low-stock items"),
    sort_by: str = Query("product_id", pattern="^(product_id|quantity|updated_at|id)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Inventory)
    if low_stock_only:
        query = query.filter(Inventory.quantity <= Inventory.low_stock_threshold)
    total = query.count()
    sort_col = getattr(Inventory, sort_by)
    order_func = asc if sort_order == "asc" else desc
    items = (
        query.order_by(order_func(sort_col))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(
        items=[_enrich(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get(
    "/low-stock",
    response_model=list[LowStockAlert],
    summary="Get all products below their low-stock threshold",
    description="Returns a denormalized list of all products whose current quantity "
    "is at or below their configured low_stock_threshold.",
)
def get_low_stock_alerts(db: Session = Depends(get_db)):
    results = (
        db.query(Inventory)
        .options(joinedload(Inventory.product))
        .filter(Inventory.quantity <= Inventory.low_stock_threshold)
        .all()
    )
    return [
        LowStockAlert(
            product_id=r.product_id,
            product_name=r.product.name,
            sku=r.product.sku,
            current_quantity=r.quantity,
            threshold=r.low_stock_threshold,
            warehouse_location=r.warehouse_location,
        )
        for r in results
    ]


@router.get(
    "/{inventory_id}",
    response_model=InventoryResponse,
    summary="Get a single inventory record",
    responses={404: {"model": ErrorResponse, "description": "Inventory record not found"}},
)
def get_inventory(inventory_id: int, db: Session = Depends(get_db)):
    inv = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inventory record not found"
        )
    return _enrich(inv)


@router.post(
    "",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an inventory record for a product",
    description="Creates a one-to-one inventory record for a product. "
    "Returns 409 if the product already has an inventory record.",
    responses={
        404: {"model": ErrorResponse, "description": "Product not found"},
        409: {"model": ErrorResponse, "description": "Inventory record already exists for this product"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def create_inventory(
    payload: InventoryCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    if not db.query(Product).filter(Product.id == payload.product_id).first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    if db.query(Inventory).filter(Inventory.product_id == payload.product_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inventory record already exists for this product",
        )
    inv = Inventory(**payload.model_dump())
    if inv.quantity > 0:
        inv.last_restocked = datetime.now(timezone.utc)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _enrich(inv)


@router.put(
    "/{inventory_id}",
    response_model=InventoryResponse,
    summary="Update an inventory record",
    responses={
        404: {"model": ErrorResponse, "description": "Inventory record not found"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def update_inventory(
    inventory_id: int,
    payload: InventoryUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    inv = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inventory record not found"
        )
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(inv, key, value)
    db.commit()
    db.refresh(inv)
    return _enrich(inv)


@router.post(
    "/{inventory_id}/adjust",
    response_model=InventoryResponse,
    summary="Adjust inventory quantity (restock or consume)",
    description="Applies a signed delta to the current quantity. Positive values add stock, "
    "negative values remove it. Rejects if resulting quantity would be negative. "
    "Triggers an async low-stock alert check after the adjustment.",
    responses={
        400: {"model": ErrorResponse, "description": "Insufficient stock for negative adjustment"},
        404: {"model": ErrorResponse, "description": "Inventory record not found"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def adjust_inventory(
    inventory_id: int,
    payload: InventoryAdjust,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    inv = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Inventory record not found"
        )
    new_qty = inv.quantity + payload.adjustment
    if new_qty < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Current: {inv.quantity}, adjustment: {payload.adjustment}",
        )
    inv.quantity = new_qty
    if payload.adjustment > 0:
        inv.last_restocked = datetime.now(timezone.utc)
    db.commit()
    db.refresh(inv)

    # Background task: check for low stock and log warning
    background_tasks.add_task(
        check_low_stock_alerts, inv.product_id, settings.DATABASE_URL
    )

    logger.info(
        "Inventory adjusted for product_id=%d: %+d units (%s). New quantity: %d",
        inv.product_id,
        payload.adjustment,
        payload.reason,
        inv.quantity,
    )
    return _enrich(inv)
