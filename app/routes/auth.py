"""Authentication routes: register, login, token refresh.

Contract:
  Input:  UserCreate | LoginRequest | TokenRefresh payloads.
  Output: UserResponse (register) | Token (login, refresh).
  Precondition: email/username unique (register); valid credentials (login);
                valid refresh token (refresh).
  Postcondition: new user row (register); JWT pair issued (login/refresh).
  Side effects: password hashed with bcrypt on register.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.user import (
    LoginRequest,
    Token,
    TokenRefresh,
    UserCreate,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description="Creates a new user with a bcrypt-hashed password. "
    "Returns 409 if the email or username is already taken.",
    responses={
        409: {"model": ErrorResponse, "description": "Email or username already exists"},
        422: {"description": "Validation error (missing/invalid fields)"},
    },
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )
    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate and receive tokens",
    description="Validates username + password and returns a JWT access/refresh pair. "
    "Access token expires in 30 minutes; refresh token in 7 days.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        403: {"model": ErrorResponse, "description": "Account deactivated"},
    },
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    return Token(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )


@router.post(
    "/refresh",
    response_model=Token,
    summary="Refresh an expired access token",
    description="Accepts a valid refresh token and returns a new access/refresh pair. "
    "The old refresh token remains valid until its own expiry.",
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or expired refresh token"},
    },
)
def refresh_token(payload: TokenRefresh, db: Session = Depends(get_db)):
    token_data = decode_token(payload.refresh_token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    if token_data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type, expected refresh token",
        )
    user_id = token_data.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )
    return Token(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )
