"""Auth endpoints: register, verify email, login, get current user."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.models import User
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    send_verification_email,
)
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


@router.post("/register", status_code=201)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new user with username, email, and password."""
    if len(payload.username) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if "@" not in payload.email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    # Check uniqueness
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Username already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    token = secrets.token_urlsafe(32)
    skip_verification = not settings.SMTP_HOST

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_verified=skip_verification,
        verification_token=None if skip_verification else token,
    )
    db.add(user)
    db.commit()

    if not skip_verification:
        try:
            send_verification_email(payload.email, token)
        except Exception:
            pass  # Don't fail registration if email fails

    msg = "Account created."
    if skip_verification:
        msg += " You can now sign in."
    else:
        msg += " Check your email to verify your account."

    return {"message": msg, "username": payload.username}


@router.get("/verify")
def verify_email(token: str, db: Session = Depends(get_db)):
    """Verify email address using the token from the verification link."""
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user.is_verified = True
    user.verification_token = None
    db.commit()

    return {"message": "Email verified. You can now sign in."}


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate with username and password."""
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before signing in",
        )

    token = create_access_token(form_data.username)
    return TokenResponse(access_token=token, username=form_data.username)


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat(),
    }
