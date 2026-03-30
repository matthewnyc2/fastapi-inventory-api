"""Inventory Pydantic schemas with full validation and OpenAPI metadata."""

from datetime import datetime

from pydantic import BaseModel, Field


class InventoryCreate(BaseModel):
    """Create an inventory record for a product. One record per product (enforced unique)."""

    product_id: int = Field(
        ..., gt=0,
        description="FK to an existing product that has no inventory record yet",
        examples=[1],
    )
    quantity: int = Field(
        ..., ge=0, le=9999999,
        description="Initial stock quantity on hand",
        examples=[100],
    )
    low_stock_threshold: int = Field(
        10, ge=0, le=9999999,
        description="Quantity at or below which a low-stock alert fires",
        examples=[10],
    )
    warehouse_location: str | None = Field(
        None, max_length=100,
        description="Physical warehouse location code",
        examples=["A1-01"],
    )


class InventoryUpdate(BaseModel):
    """Partial update for an inventory record. Only provided fields are changed."""

    quantity: int | None = Field(None, ge=0, le=9999999)
    low_stock_threshold: int | None = Field(None, ge=0, le=9999999)
    warehouse_location: str | None = Field(None, max_length=100)


class InventoryAdjust(BaseModel):
    """Adjust inventory by a signed delta. Positive adds stock, negative removes it.

    The resulting quantity must remain >= 0 or the request is rejected.
    """

    adjustment: int = Field(
        ...,
        description="Signed quantity change (positive = restock, negative = consume)",
        examples=[50],
    )
    reason: str = Field(
        ..., min_length=1, max_length=500,
        description="Audit-trail reason for this adjustment",
        examples=["Shipment from supplier received"],
    )


class InventoryResponse(BaseModel):
    """Inventory record as returned by the API, with computed low-stock flag."""

    id: int = Field(..., examples=[1])
    product_id: int = Field(..., examples=[1])
    quantity: int = Field(..., examples=[150])
    low_stock_threshold: int = Field(..., examples=[20])
    warehouse_location: str | None = Field(None, examples=["A1-01"])
    last_restocked: datetime | None = Field(None, description="Timestamp of last positive stock adjustment")
    updated_at: datetime
    is_low_stock: bool = Field(False, description="True when quantity <= low_stock_threshold")

    model_config = {"from_attributes": True}


class LowStockAlert(BaseModel):
    """Denormalized alert for a product that is at or below its stock threshold."""

    product_id: int = Field(..., examples=[4])
    product_name: str = Field(..., examples=["27\" IPS Monitor"])
    sku: str = Field(..., examples=["ELEC-004"])
    current_quantity: int = Field(..., examples=[3])
    threshold: int = Field(..., examples=[5])
    warehouse_location: str | None = Field(None, examples=["A1-04"])
