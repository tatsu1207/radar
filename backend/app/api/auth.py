"""Auth endpoints: login with Linux credentials, get current user."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.models import User
from app.core.auth import authenticate_pam, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class UserRead(BaseModel):
    id: str
    username: str
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate with Linux username and password."""
    if not authenticate_pam(form_data.username, form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Get or create user record
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user:
        user = User(username=form_data.username)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(form_data.username)
    return TokenResponse(access_token=token, username=form_data.username)


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "created_at": current_user.created_at.isoformat(),
    }
