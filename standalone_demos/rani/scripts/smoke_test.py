"""
In-process smoke test against whatever DATABASE_URL points to (used by CI for PostgreSQL).
Creates a temporary admin, pushes simulated + replayed events through the real pipeline,
checks reconciliation and the audit chain, and prints a summary.
"""

from __future__ import annotations

import json
import os
import secrets
import sys

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.models import User
from backend.security import hash_password


def main() -> int:
    s = Settings.from_env(secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32), alerts_sync=True)
    app = create_app(s)
    user, pw = f"smoke-{secrets.token_hex(3)}", secrets.token_urlsafe(16)
    with app.state.db.session() as db:
        db.add(User(username=user, full_name="CI smoke", role="admin", password_hash=hash_password(pw, 1000)))
    c = TestClient(app)
    h = {
        "Authorization": "Bearer "
        + c.post("/api/v1/auth/login", json={"username": user, "password": pw}).json()["access_token"]
    }
    sim = c.post(
        "/api/v1/demo/run",
        json={"mode": "simulate", "count": 30, "scenario": "mixed", "seed": secrets.randbelow(10**6)},
        headers=h,
    ).json()
    rep = c.post(
        "/api/v1/demo/run", json={"mode": "replay", "count": 20, "seed": secrets.randbelow(10**6)}, headers=h
    ).json()
    summ = c.get("/api/v1/dashboard/summary", headers=h).json()
    ver = c.get("/api/v1/audit/verify", headers=h).json()
    ok = (
        sim["failed"] == 0
        and rep["failed"] == 0
        and ver["valid"]
        and all(v for v in summ["reconciliation"].values() if isinstance(v, bool))
    )
    print(
        json.dumps(
            {
                "database": app.state.db.engine.dialect.name,
                "simulate": sim,
                "replay": rep,
                "events_total": summ["events"]["total"],
                "reasons": summ["decisions"]["by_reason"],
                "reconciliation": summ["reconciliation"],
                "audit": ver,
                "ok": ok,
            },
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
