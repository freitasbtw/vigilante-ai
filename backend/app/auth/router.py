"""Auth endpoints: register, login, refresh, me."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.security import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.db.base import get_session
from app.db.entities import Tenant, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    tenant_name: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str
    created_at: datetime


@router.post("/register", response_model=TokenPair, status_code=201)
def register(
    req: RegisterRequest, session: Session = Depends(get_session)
) -> TokenPair:
    if not settings.ALLOW_OPEN_REGISTRATION:
        raise HTTPException(status_code=403, detail="Registration disabled")

    existing = session.scalar(select(User).where(User.email == req.email))
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    tenant = Tenant(name=req.tenant_name)
    session.add(tenant)
    session.flush()

    user = User(
        tenant_id=tenant.id,
        email=req.email,
        password_hash=hash_password(req.password),
        role=ROLE_ADMIN,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return TokenPair(
        access_token=create_access_token(sub=user.id, tenant_id=user.tenant_id, role=user.role),
        refresh_token=create_refresh_token(sub=user.id, tenant_id=user.tenant_id),
    )


@router.post("/login", response_model=TokenPair)
def login(req: LoginRequest, session: Session = Depends(get_session)) -> TokenPair:
    user = session.scalar(select(User).where(User.email == req.email))
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return TokenPair(
        access_token=create_access_token(sub=user.id, tenant_id=user.tenant_id, role=user.role),
        refresh_token=create_refresh_token(sub=user.id, tenant_id=user.tenant_id),
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(
    req: RefreshRequest, session: Session = Depends(get_session)
) -> TokenPair:
    try:
        payload = decode_token(req.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Malformed token")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return TokenPair(
        access_token=create_access_token(sub=user.id, tenant_id=user.tenant_id, role=user.role),
        refresh_token=create_refresh_token(sub=user.id, tenant_id=user.tenant_id),
    )


@router.get("/me", response_model=MeResponse)
def me(
    current: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MeResponse:
    user = session.get(User, current.id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        created_at=user.created_at,
    )
