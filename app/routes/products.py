"""CRUD routes for products.

Contract:
  Input:  ProductCreate | ProductUpdate payloads; path param product_id.
  Output: ProductResponse (single) | PaginatedResponse[ProductResponse] (list).
  Precondition: SKU unique; category_id FK valid; product exists for get/update/delete.
  Postcondition: row created/updated/deleted in products table.
  Side effects: none.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])


@router.get(
    "",
    response_model=PaginatedResponse[ProductResponse],
    summary="List products with filtering, sorting, and pagination",
    description="Returns a paginated product list. Supports text search (name/SKU), "
    "category filter, price range, and configurable sort order.",
)
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    search: str | None = Query(None, description="Search by name or SKU"),
    category_id: int | None = Query(None, description="Filter by category ID"),
    min_price: float | None = Query(None, ge=0, description="Minimum price filter"),
    max_price: float | None = Query(None, ge=0, description="Maximum price filter"),
    sort_by: str = Query("name", pattern="^(name|price|sku|created_at|id)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Product).options(joinedload(Product.category))
    if search:
        query = query.filter(
            (Product.name.ilike(f"%{search}%")) | (Product.sku.ilike(f"%{search}%"))
        )
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    total = query.count()
    sort_col = getattr(Product, sort_by)
    order_func = asc if sort_order == "asc" else desc
    items = (
        query.order_by(order_func(sort_col))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get a single product",
    responses={404: {"model": ErrorResponse, "description": "Product not found"}},
)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = (
        db.query(Product)
        .options(joinedload(Product.category))
        .filter(Product.id == product_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product",
    description="Creates a product with a unique SKU under an existing category.",
    responses={
        404: {"model": ErrorResponse, "description": "Category not found"},
        409: {"model": ErrorResponse, "description": "SKU already exists"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    if not db.query(Category).filter(Category.id == payload.category_id).first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    if db.query(Product).filter(Product.sku == payload.sku).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product with this SKU already exists",
        )
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    # Reload with category relationship
    product = (
        db.query(Product)
        .options(joinedload(Product.category))
        .filter(Product.id == product.id)
        .first()
    )
    return product


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update a product",
    responses={
        404: {"model": ErrorResponse, "description": "Product or category not found"},
        409: {"model": ErrorResponse, "description": "SKU conflict with another product"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    update_data = payload.model_dump(exclude_unset=True)
    if "category_id" in update_data:
        if not db.query(Category).filter(Category.id == update_data["category_id"]).first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )
    if "sku" in update_data:
        existing = db.query(Product).filter(
            Product.sku == update_data["sku"], Product.id != product_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product with this SKU already exists",
            )
    for key, value in update_data.items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    product = (
        db.query(Product)
        .options(joinedload(Product.category))
        .filter(Product.id == product.id)
        .first()
    )
    return product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product",
    responses={
        404: {"model": ErrorResponse, "description": "Product not found"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    db.delete(product)
    db.commit()
