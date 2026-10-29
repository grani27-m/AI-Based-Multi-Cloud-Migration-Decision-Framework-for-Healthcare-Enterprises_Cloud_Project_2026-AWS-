"""Authentication and user management.  Owner: Rani Gupta"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.audit import write_audit
from backend.deps import get_db, get_principal, require
from backend.models import User
from backend.schemas import LoginIn, UserCreate, UserOut
from backend.security import Principal, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1", tags=["auth"])
_DUMMY_HASH = hash_password("timing-equaliser-password", 1000)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = request.app.state.settings
    u = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    ok = verify_password(body.password, u.password_hash if u else _DUMMY_HASH)
    if not u or not ok or not u.is_active:
        write_audit(db, body.username[:64], "login_failed", "auth", {})
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    token, exp = create_access_token(u.id, u.username, u.role, s.secret_key, s.jwt_issuer, s.jwt_audience,
                                     s.access_token_minutes)
    u.last_login_at = datetime.now(timezone.utc)
    write_audit(db, u.username, "login", "auth", {"role": u.role})
    return {"access_token": token, "token_type": "bearer", "expires_at": exp.isoformat(),
            "user": {"id": u.id, "username": u.username, "role": u.role, "full_name": u.full_name}}


@router.get("/auth/me")
def me(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    u = db.get(User, p.user_id)
    return {"id": u.id, "username": u.username, "role": u.role, "full_name": u.full_name}


@router.get("/users", response_model=list[UserOut])
def list_users(_: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    return db.execute(select(User).order_by(User.id)).scalars().all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, p: Principal = Depends(require("users:manage")),
                db: Session = Depends(get_db)):
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists")
    u = User(username=body.username, full_name=body.full_name, role=body.role,
             password_hash=hash_password(body.password, request.app.state.settings.password_iterations))
    db.add(u)
    db.flush()
    write_audit(db, p.username, "user_created", f"user/{u.id}", {"username": u.username, "role": u.role})
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, is_active: bool | None = None, role: str | None = None,
                p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    if u.id == p.user_id and (is_active is False or (role and role != "admin")):
        raise HTTPException(400, "admins cannot deactivate or demote themselves")
    if role is not None:
        if role not in ("admin", "doctor", "auditor", "device"):
            raise HTTPException(422, "invalid role")
        u.role = role
    if is_active is not None:
        u.is_active = is_active
    write_audit(db, p.username, "user_updated", f"user/{u.id}", {"is_active": u.is_active, "role": u.role})
    return u
