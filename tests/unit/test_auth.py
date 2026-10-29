"""Rani: password hashing, JWT validation (valid/invalid/expired/tampered) and the full role matrix."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from backend.security import PERMISSIONS, create_access_token, hash_password, verify_password
from tests.conftest import event, login


def test_password_hash_roundtrip_and_salting():
    h1, h2 = hash_password("s3cret-passw0rd", 1000), hash_password("s3cret-passw0rd", 1000)
    assert h1 != h2 and h1.startswith("pbkdf2_sha256$1000$")
    assert verify_password("s3cret-passw0rd", h1) and not verify_password("wrong-password", h1)
    assert not verify_password("x", "garbage")
    with pytest.raises(ValueError):
        hash_password("short")


def test_login_success_and_failure(client):
    assert client.post("/api/v1/auth/login", json={"username": "admin1", "password": "nope-nope"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope-nope"}).status_code == 401
    h = login(client, "admin1")
    assert client.get("/api/v1/auth/me", headers=h).json()["role"] == "admin"


def test_missing_malformed_and_tampered_tokens(client, headers):
    assert client.get("/api/v1/events").status_code == 401
    assert client.get("/api/v1/events", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
    tok = headers["admin"]["Authorization"].split()[1]
    head, body, sig = tok.split(".")
    tampered = f"{head}.{body}.{sig[:-2]}{'A' if sig[-2] != 'A' else 'B'}{sig[-1]}"
    assert client.get("/api/v1/events", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_expired_token_rejected(client, app):
    s = app.state.settings
    tok = jwt.encode({"sub": "1", "username": "admin1", "role": "admin", "iss": s.jwt_issuer, "aud": s.jwt_audience,
                      "iat": datetime.now(timezone.utc) - timedelta(hours=2),
                      "exp": datetime.now(timezone.utc) - timedelta(hours=1)}, s.secret_key, algorithm="HS256")
    r = client.get("/api/v1/events", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401 and r.json()["detail"] == "token expired"


def test_wrong_secret_or_audience_rejected(client, app):
    s = app.state.settings
    bad_key, _ = create_access_token(1, "admin1", "admin", "another-secret-" + "y" * 40, s.jwt_issuer, s.jwt_audience, 5)
    bad_aud, _ = create_access_token(1, "admin1", "admin", s.secret_key, s.jwt_issuer, "other-api", 5)
    for t in (bad_key, bad_aud):
        assert client.get("/api/v1/events", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_deactivated_user_loses_access_immediately(client, headers):
    users = client.get("/api/v1/users", headers=headers["admin"]).json()
    doc = next(u for u in users if u["username"] == "doc1")
    assert client.patch(f"/api/v1/users/{doc['id']}?is_active=false", headers=headers["admin"]).status_code == 200
    assert client.get("/api/v1/events", headers=headers["doctor"]).status_code == 401


ENDPOINTS = {  # permission -> (method, path, body)
    "events:create": ("post", "/api/v1/events", event("rbac-evt-1")),
    "records:read": ("get", "/api/v1/dashboard/summary", None),
    "audit:read": ("get", "/api/v1/audit/verify", None),
    "users:manage": ("get", "/api/v1/users", None),
    "demo:run": ("post", "/api/v1/demo/run", {"mode": "simulate", "count": 1, "seed": 99}),
}


@pytest.mark.parametrize("perm", list(ENDPOINTS))
@pytest.mark.parametrize("role", ["admin", "doctor", "auditor", "device"])
def test_role_matrix(client, headers, perm, role):
    method, path, body = ENDPOINTS[perm]
    if perm == "events:create":
        body = {**body, "event_id": f"rbac-{role}"}
    r = getattr(client, method)(path, headers=headers[role], **({"json": body} if body else {}))
    if role in PERMISSIONS[perm]:
        assert r.status_code in (200, 201), r.text
    else:
        assert r.status_code == 403


def test_alert_ack_permissions(client, headers):
    client.post("/api/v1/events", json=event("ack-1", criticality=9.9), headers=headers["device"])
    aid = client.get("/api/v1/alerts", headers=headers["auditor"]).json()["items"][0]["id"]
    assert client.post(f"/api/v1/alerts/{aid}/ack", headers=headers["auditor"]).status_code == 403
    assert client.post(f"/api/v1/alerts/{aid}/ack", headers=headers["doctor"]).status_code == 200


def test_admin_cannot_demote_self(client, headers):
    me = client.get("/api/v1/auth/me", headers=headers["admin"]).json()
    assert client.patch(f"/api/v1/users/{me['id']}?role=auditor", headers=headers["admin"]).status_code == 400


def test_create_user_validation(client, headers):
    ok = client.post("/api/v1/users", json={"username": "nurse.a", "password": "long-enough-pw", "role": "doctor"},
                     headers=headers["admin"])
    assert ok.status_code == 201 and "password" not in ok.text
    dup = client.post("/api/v1/users", json={"username": "nurse.a", "password": "long-enough-pw", "role": "doctor"},
                      headers=headers["admin"])
    assert dup.status_code == 409
    weak = client.post("/api/v1/users", json={"username": "nurse.b", "password": "short", "role": "doctor"},
                       headers=headers["admin"])
    assert weak.status_code == 422
