"""
backend/deps.py  —  Owner: Rani Gupta
======================================
FastAPI dependencies: DB session, authenticated principal, permission checks,
per-user rate limiting.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Iterator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.models import User
from backend.security import PERMISSIONS, Principal, decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.db.session() as s:
        yield s


def get_principal(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "invalid or missing bearer token", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None or creds.scheme.lower() != "bearer":
        raise unauthorized
    s = request.app.state.settings
    try:
        p = decode_access_token(creds.credentials, s.secret_key, s.jwt_issuer, s.jwt_audience)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "token expired", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    except jwt.PyJWTError:
        raise unauthorized from None
    # Own short session (not the request-scoped one): on SQLite every transaction takes the write lock, so the
    # auth check must not keep a transaction open while the pipeline runs its own transactions.
    with request.app.state.db.session() as db:
        u = db.get(User, p.user_id)
        active = u is not None and u.is_active and u.role == p.role
    if not active:  # deactivated users / changed roles lose access at once
        raise unauthorized
    return p


def require(permission: str):
    allowed = PERMISSIONS[permission]

    def _dep(p: Principal = Depends(get_principal)) -> Principal:
        if p.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"role '{p.role}' may not perform '{permission}'")
        return p

    return _dep


class RateLimiter:
    """Sliding 60-second window per user (per process; behind several workers use a gateway limit)."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[int, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, user_id: int) -> None:
        now = time.monotonic()
        with self.lock:
            q = self.hits[user_id]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded", headers={"Retry-After": "60"}
                )
            q.append(now)
