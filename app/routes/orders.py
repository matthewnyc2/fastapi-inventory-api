"""CRUD routes for order management.

Contract:
  Input:  OrderCreate | OrderStatusUpdate payloads; path param order_id.
  Output: OrderResponse (single) | PaginatedResponse[OrderResponse] (list).
  Precondition: all product_id FKs valid; sufficient inventory for each line item;
                valid status transition for updates; order exists for get/update/delete.
  Postcondition: inventory deducted on create; inventory restored on cancel/delete;
                 status transitions enforced (pending->confirmed->shipped->delivered).
  Side effects: inventory quantity changes on create, cancel, and delete.
"""

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.order import OrderCreate, OrderResponse, OrderStatusUpdate

router = APIRouter(prefix="/orders", tags=["Orders"])


def _generate_order_number() -> str:
    return f"ORD-{uuid.uuid4().hex[:8].upper()}"


@router.get(
    "",
    response_model=PaginatedResponse[OrderResponse],
    summary="List orders with filtering, sorting, and pagination",
    description="Returns paginated orders with nested line items. "
    "Filterable by status and customer email. Requires authentication.",
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    status_filter: str | None = Query(
        None,
        alias="status",
        pattern="^(pending|confirmed|shipped|delivered|cancelled)$",
        description="Filter by order status",
    ),
    customer_email: str | None = Query(None, description="Filter by customer email"),
    sort_by: str = Query("created_at", pattern="^(created_at|total_amount|order_number|id)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = db.query(Order).options(joinedload(Order.items))
    if status_filter:
        query = query.filter(Order.status == status_filter)
    if customer_email:
        query = query.filter(Order.customer_email.ilike(f"%{customer_email}%"))
    total = query.count()
    sort_col = getattr(Order, sort_by)
    order_func = asc if sort_order == "asc" else desc
    items = (
        query.order_by(order_func(sort_col))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    # Deduplicate due to joinedload producing duplicates with pagination
    seen = set()
    unique_items = []
    for item in items:
        if item.id not in seen:
            seen.add(item.id)
            unique_items.append(item)
    return PaginatedResponse(
        items=unique_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get a single order with items",
    responses={
        404: {"model": ErrorResponse, "description": "Order not found"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    order = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place a new order (validates stock and deducts inventory)",
    description="Validates that all products exist and have sufficient inventory, "
    "deducts stock atomically, computes total, and returns the new order with status 'pending'.",
    responses={
        400: {"model": ErrorResponse, "description": "Insufficient stock for one or more items"},
        404: {"model": ErrorResponse, "description": "Product not found"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    order = Order(
        order_number=_generate_order_number(),
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        notes=payload.notes,
        status="pending",
    )
    total = 0.0
    for line in payload.items:
        product = db.query(Product).filter(Product.id == line.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product ID {line.product_id} not found",
            )
        # Check and deduct inventory
        inv = db.query(Inventory).filter(Inventory.product_id == line.product_id).first()
        if not inv or inv.quantity < line.quantity:
            available = inv.quantity if inv else 0
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient stock for '{product.name}' (SKU: {product.sku}). "
                    f"Requested: {line.quantity}, Available: {available}"
                ),
            )
        inv.quantity -= line.quantity
        subtotal = product.price * line.quantity
        total += subtotal
        order.items.append(
            OrderItem(
                product_id=product.id,
                quantity=line.quantity,
                unit_price=product.price,
                subtotal=subtotal,
            )
        )
    order.total_amount = round(total, 2)
    db.add(order)
    db.commit()
    db.refresh(order)
    # Reload with items
    order = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.id == order.id)
        .first()
    )
    return order


@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
    summary="Update order status",
    description="Transitions the order to the target status. Only valid transitions are allowed: "
    "pending->confirmed|cancelled, confirmed->shipped|cancelled, shipped->delivered. "
    "Cancellation restores inventory for all line items.",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid status transition"},
        404: {"model": ErrorResponse, "description": "Order not found"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    order = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # Validate status transitions
    valid_transitions = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"shipped", "cancelled"},
        "shipped": {"delivered"},
        "delivered": set(),
        "cancelled": set(),
    }
    if payload.status not in valid_transitions.get(order.status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from '{order.status}' to '{payload.status}'",
        )

    # If cancelling, restore inventory
    if payload.status == "cancelled":
        for item in order.items:
            inv = db.query(Inventory).filter(Inventory.product_id == item.product_id).first()
            if inv:
                inv.quantity += item.quantity

    order.status = payload.status
    db.commit()
    db.refresh(order)
    return order


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an order (only pending orders)",
    description="Permanently removes a pending order and restores inventory for all line items. "
    "Orders in any other status cannot be deleted.",
    responses={
        400: {"model": ErrorResponse, "description": "Only pending orders can be deleted"},
        404: {"model": ErrorResponse, "description": "Order not found"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending orders can be deleted",
        )
    # Restore inventory before deletion
    for item in order.items:
        inv = db.query(Inventory).filter(Inventory.product_id == item.product_id).first()
        if inv:
            inv.quantity += item.quantity
    db.delete(order)
    db.commit()
