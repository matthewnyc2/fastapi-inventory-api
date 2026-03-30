"""Product Pydantic schemas with full validation and OpenAPI metadata."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.category import CategoryResponse


class ProductCreate(BaseModel):
    """Payload to create a new product. SKU must be unique across all products."""

    sku: str = Field(
        ..., min_length=1, max_length=50,
        pattern=r"^[A-Z0-9]+-[A-Z0-9]+$",
        description="Stock-keeping unit code (e.g. ELEC-001)",
        examples=["ELEC-099"],
    )
    name: str = Field(
        ..., min_length=1, max_length=200,
        description="Human-readable product name",
        examples=["Bluetooth Speaker"],
    )
    description: str | None = Field(
        None, max_length=1000,
        description="Optional detailed product description",
        examples=["Portable 20W speaker with 12-hour battery"],
    )
    price: float = Field(
        ..., gt=0, le=999999.99,
        description="Unit price in USD, must be positive",
        examples=[45.99],
    )
    category_id: int = Field(
        ..., gt=0,
        description="FK to an existing category",
        examples=[1],
    )


class ProductUpdate(BaseModel):
    """Partial update payload. Only provided fields are changed."""

    sku: str | None = Field(
        None, min_length=1, max_length=50,
        pattern=r"^[A-Z0-9]+-[A-Z0-9]+$",
        description="Updated SKU (must remain unique)",
    )
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    price: float | None = Field(None, gt=0, le=999999.99)
    category_id: int | None = Field(None, gt=0)


class ProductResponse(BaseModel):
    """Product resource as returned by the API, optionally including nested category."""

    id: int = Field(..., examples=[1])
    sku: str = Field(..., examples=["ELEC-001"])
    name: str = Field(..., examples=["Wireless Mouse"])
    description: str | None = Field(None, examples=["Ergonomic 2.4GHz wireless mouse"])
    price: float = Field(..., examples=[29.99])
    category_id: int = Field(..., examples=[1])
    category: CategoryResponse | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
