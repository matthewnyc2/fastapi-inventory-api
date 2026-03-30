"""Category Pydantic schemas with full validation and OpenAPI metadata."""

from datetime import datetime

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    """Payload to create a new product category. Name must be unique."""

    name: str = Field(
        ..., min_length=1, max_length=100,
        description="Unique category name",
        examples=["Electronics"],
    )
    description: str | None = Field(
        None, max_length=500,
        description="Optional description of the category",
        examples=["Electronic devices, components, and accessories"],
    )


class CategoryUpdate(BaseModel):
    """Partial update payload. Only provided fields are changed."""

    name: str | None = Field(
        None, min_length=1, max_length=100,
        description="New unique name for the category",
    )
    description: str | None = Field(
        None, max_length=500,
        description="Updated description",
    )


class CategoryResponse(BaseModel):
    """Category resource as returned by the API."""

    id: int = Field(..., description="Auto-generated primary key", examples=[1])
    name: str = Field(..., examples=["Electronics"])
    description: str | None = Field(None, examples=["Electronic devices and accessories"])
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
