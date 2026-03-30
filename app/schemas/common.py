"""Common schemas for pagination and responses."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope for paginated list endpoints."""

    items: list[T]
    total: int = Field(..., description="Total number of records matching the query", examples=[42])
    page: int = Field(..., description="Current page number (1-indexed)", examples=[1])
    page_size: int = Field(..., description="Number of records per page", examples=[20])
    total_pages: int = Field(..., description="Total number of pages", examples=[3])


class MessageResponse(BaseModel):
    """Generic message response for non-resource operations."""

    message: str = Field(..., examples=["Operation completed successfully"])
    detail: str | None = Field(None, examples=["Additional context about the operation"])


class ErrorResponse(BaseModel):
    """Standard error response body returned by all error status codes."""

    detail: str = Field(..., examples=["Resource not found"])
