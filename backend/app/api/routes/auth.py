from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user, permissions_for_role, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas import LoginRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "active": user.active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "permissions": sorted(permissions_for_role(user.role)),
    }


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou senha invalidos.")
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": serialize_user(user)}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return serialize_user(user)
