"""
Authentication endpoints - JWT token management.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token, get_current_user_id,
)
from app.models.user import User, UserRole

logger = structlog.get_logger()
router = APIRouter()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24 hours


class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str | None
    role: UserRole
    is_active: bool

    class Config:
        from_attributes = True


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/token", response_model=TokenResponse, summary="Get JWT access token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate and get JWT access + refresh tokens.

    Use the token in subsequent requests as: `Authorization: Bearer <token>`
    """
    result = await db.execute(
        select(User).where(
            (User.email == form_data.username) | (User.username == form_data.username)
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    access_token = create_access_token(
        str(user.id),
        extra_claims={"role": user.role, "email": user.email},
    )
    refresh_token = create_refresh_token(str(user.id))

    logger.info("User logged in", user_id=str(user.id), email=user.email)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
             summary="Register new user")
async def register(
    user_in: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    # Check for existing user
    existing = await db.execute(
        select(User).where(
            (User.email == user_in.email) | (User.username == user_in.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered",
        )

    user = User(
        email=str(user_in.email),
        username=user_in.username,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=UserRole.READONLY,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("New user registered", email=user.email)
    return user


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Get a new access token using a refresh token."""
    payload = decode_token(request.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    access_token = create_access_token(
        str(user.id),
        extra_claims={"role": user.role, "email": user.email},
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserResponse, summary="Get current user")
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get the currently authenticated user's profile."""
    import uuid as _uuid
    user = await db.get(User, _uuid.UUID(current_user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
