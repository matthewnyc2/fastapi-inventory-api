"""Order Pydantic schemas with full validation and OpenAPI metadata."""

from datetime import datetime

from pydantic import BaseModel, Field


class OrderItemCreate(BaseModel):
    """A single line item within an order creation request."""

    product_id: int = Field(
        ..., gt=0,
        description="FK to an existing product",
        examples=[1],
    )
    quantity: int = Field(
        ..., gt=0, le=10000,
        description="Number of units to order (must have sufficient stock)",
        examples=[5],
    )


class OrderItemResponse(BaseModel):
    """Line item as stored on the order, with captured unit price."""

    id: int = Field(..., examples=[1])
    product_id: int = Field(..., examples=[1])
    quantity: int = Field(..., examples=[5])
    unit_price: float = Field(..., description="Price per unit at time of order", examples=[29.99])
    subtotal: float = Field(..., description="quantity * unit_price", examples=[149.95])

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    """Place a new order. Stock is validated and deducted atomically.

    Precondition: every product_id must exist and have sufficient inventory.
    Postcondition: inventory is reduced by the ordered quantities; order status is 'pending'.
    """

    customer_name: str = Field(
        ..., min_length=1, max_length=200,
        description="Name of the ordering party",
        examples=["Acme Corp"],
    )
    customer_email: str = Field(
        ..., min_length=5, max_length=255,
        description="Contact email for order notifications",
        examples=["orders@acme.com"],
    )
    notes: str | None = Field(
        None, max_length=1000,
        description="Optional free-text instructions",
        examples=["Deliver to warehouse entrance"],
    )
    items: list[OrderItemCreate] = Field(
        ..., min_length=1,
        description="At least one line item required",
    )


class OrderStatusUpdate(BaseModel):
    """Payload for the status transition endpoint.

    Valid transitions:
      pending  -> confirmed | cancelled
      confirmed -> shipped  | cancelled
      shipped  -> delivered
      delivered -> (terminal)
      cancelled -> (terminal)

    Cancellation restores inventory for all line items.
    """

    status: str = Field(
        ...,
        pattern="^(pending|confirmed|shipped|delivered|cancelled)$",
        description="Target status (must be a valid transition from current status)",
        examples=["confirmed"],
    )


class OrderResponse(BaseModel):
    """Order resource as returned by the API, including nested line items."""

    id: int = Field(..., examples=[1])
    order_number: str = Field(..., description="Auto-generated unique order reference", examples=["ORD-A1B2C3D4"])
    customer_name: str = Field(..., examples=["Acme Corp"])
    customer_email: str = Field(..., examples=["orders@acme.com"])
    status: str = Field(..., description="Current order status", examples=["pending"])
    notes: str | None = Field(None, examples=["Deliver to warehouse entrance"])
    total_amount: float = Field(..., description="Sum of all line-item subtotals", examples=[549.85])
    items: list[OrderItemResponse] = Field(default=[], description="Order line items")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
