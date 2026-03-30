"""CRUD routes for product categories.

Contract:
  Input:  CategoryCreate | CategoryUpdate payloads; path param category_id.
  Output: CategoryResponse (single) | PaginatedResponse[CategoryResponse] (list).
  Precondition: name unique on create/update; category exists for get/update/delete.
  Postcondition: row created/updated/deleted in categories table.
  Side effects: none.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.schemas.common import ErrorResponse, PaginatedResponse

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get(
    "",
    response_model=PaginatedResponse[CategoryResponse],
    summary="List all categories with pagination",
    description="Returns a paginated, searchable, sortable list of product categories. "
    "No authentication required for read access.",
)
def list_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    search: str | None = Query(None, description="Search by name"),
    sort_by: str = Query("name", pattern="^(name|created_at|id)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    query = db.query(Category)
    if search:
        query = query.filter(Category.name.ilike(f"%{search}%"))
    total = query.count()
    sort_col = getattr(Category, sort_by)
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
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Get a single category",
    responses={404: {"model": ErrorResponse, "description": "Category not found"}},
)
def get_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new category",
    description="Creates a category with a unique name. Requires Bearer authentication.",
    responses={
        409: {"model": ErrorResponse, "description": "Category name already exists"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    if db.query(Category).filter(Category.name == payload.name).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category with this name already exists",
        )
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update a category",
    responses={
        404: {"model": ErrorResponse, "description": "Category not found"},
        409: {"model": ErrorResponse, "description": "Name conflict with another category"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data:
        existing = db.query(Category).filter(
            Category.name == update_data["name"], Category.id != category_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Category with this name already exists",
            )
    for key, value in update_data.items():
        setattr(category, key, value)
    db.commit()
    db.refresh(category)
    return category


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category",
    description="Permanently removes a category. Associated products will have a dangling FK.",
    responses={
        404: {"model": ErrorResponse, "description": "Category not found"},
        401: {"model": ErrorResponse, "description": "Missing or invalid Bearer token"},
    },
)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    db.delete(category)
    db.commit()
