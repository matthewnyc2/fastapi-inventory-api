"""User Pydantic schemas for authentication and registration."""

from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Registration payload. Password must be 8-128 characters."""

    email: str = Field(
        ..., min_length=5, max_length=255,
        description="Valid email address",
        examples=["alice@inventory.io"],
    )
    username: str = Field(
        ..., min_length=3, max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Alphanumeric username (letters, digits, hyphens, underscores)",
        examples=["alice_j"],
    )
    password: str = Field(
        ..., min_length=8, max_length=128,
        description="Plain-text password (hashed server-side with bcrypt)",
        examples=["strongpass123"],
    )
    full_name: str | None = Field(
        None, max_length=255,
        description="Optional display name",
        examples=["Alice Johnson"],
    )


class UserResponse(BaseModel):
    """Public user profile. Never exposes hashed_password."""

    id: int
    email: str
    username: str
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """JWT token pair returned on successful authentication."""

    access_token: str = Field(..., description="Short-lived access token (30 min default)")
    refresh_token: str = Field(..., description="Long-lived refresh token (7 days default)")
    token_type: str = Field("bearer", description="Token scheme, always 'bearer'")


class TokenRefresh(BaseModel):
    """Payload for the token refresh endpoint."""

    refresh_token: str = Field(..., description="The refresh token received during login")


class LoginRequest(BaseModel):
    """Credentials for the login endpoint."""

    username: str = Field(..., description="Registered username", examples=["admin"])
    password: str = Field(..., description="Account password", examples=["admin123"])
