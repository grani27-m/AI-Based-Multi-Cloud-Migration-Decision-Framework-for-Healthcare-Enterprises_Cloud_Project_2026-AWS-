"""
backend/security.py  —  Owner: Rani Gupta
==========================================
Password hashing  : PBKDF2-HMAC-SHA256, per-user 16-byte salt, 310,000 iterations
                    (OWASP 2023 recommendation), constant-time comparison.
                    Format: pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
Tokens            : JWT HS256 (PyJWT) with sub, role, iss, aud, iat, exp, jti.
Roles             : admin, doctor, auditor (people) and device (ingestion service accounts).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

ROLES = ("admin", "doctor", "auditor", "device")

# permission -> roles allowed. One table, enforced by backend/deps.py and tested in tests/unit/test_auth.py
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "events:create": ("admin", "doctor", "device"),
    "records:read": ("admin", "doctor", "auditor"),
    "alerts:ack": ("admin", "doctor"),
    "audit:read": ("admin", "auditor"),
    "users:manage": ("admin",),
    "demo:run": ("admin",),
}


def hash_password(password: str, iterations: int = 310_000) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(it))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


@dataclass
class Principal:
    user_id: int
    username: str
    role: str
    jti: str = ""


def create_access_token(user_id: int, username: str, role: str, secret: str, issuer: str, audience: str,
                        minutes: int) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=minutes)
    payload = {"sub": str(user_id), "username": username, "role": role, "iss": issuer, "aud": audience,
               "iat": now, "exp": exp, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, secret, algorithm="HS256"), exp


def decode_access_token(token: str, secret: str, issuer: str, audience: str) -> Principal:
    """Raises jwt.PyJWTError subclasses on any problem (expired, bad signature, wrong aud/iss)."""
    p = jwt.decode(token, secret, algorithms=["HS256"], issuer=issuer, audience=audience,
                   options={"require": ["exp", "iat", "sub", "iss", "aud"]})
    if p.get("role") not in ROLES:
        raise jwt.InvalidTokenError("unknown role")
    return Principal(user_id=int(p["sub"]), username=p["username"], role=p["role"], jti=p.get("jti", ""))
