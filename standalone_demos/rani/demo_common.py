"""Helpers shared by Rani's demo scripts (package-only file)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)  # relative paths in .env (runtime/app.db) always resolve inside this package
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env() -> dict:
    from backend.config import _load_dotenv

    _load_dotenv(ROOT / ".env")
    return dict(os.environ)


def require_env(*names: str) -> None:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(f"missing {', '.join(missing)} in .env - run: python 00_setup_env.py")


def api_url() -> str:
    return os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")


def login(client, username: str, password: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        raise SystemExit(f"login as {username} failed: HTTP {r.status_code} {r.text[:200]}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def wait_ready(base: str, timeout: float = 60.0) -> bool:
    import time

    import httpx

    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if httpx.get(base + "/ready", timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def server_running(base: str) -> bool:
    import httpx

    try:
        return httpx.get(base + "/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False
