"""Shared pytest fixtures. Test data here is SYNTHETIC and only used for automated tests."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.security import hash_password  # noqa: E402


class FakeChannel:
    """In-memory notification channel; never contacts a real provider."""

    def __init__(self, name="fake", fail_times=0, configured=True):
        self.name, self.fail_times, self._configured, self.sent = name, fail_times, configured, []

    def configured(self):
        return self._configured

    def send(self, alert):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise TimeoutError("simulated provider timeout")
        self.sent.append(alert.message)
        return "fake ok"


def make_settings(tmp_path: Path, **kw) -> Settings:
    s = Settings.from_env(
        environment="test", database_url=f"sqlite:///{tmp_path / 'test.db'}", secret_key="test-secret-" + "x" * 40,
        password_iterations=1000, runtime_dir=tmp_path / "runtime", alerts_sync=True,
        bootstrap_admin_username="", bootstrap_admin_password="", frontend_dist=tmp_path / "no-dist",
        cors_origins=["http://localhost:5173"], rate_limit_per_minute=10_000)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def add_user(app, username, role, password="correct-horse-battery"):
    from backend.models import User
    with app.state.db.session() as db:
        db.add(User(username=username, role=role, full_name=username, password_hash=hash_password(password, 1000)))
    return password


def login(client, username, password="correct-horse-battery") -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def channel():
    return FakeChannel()


@pytest.fixture
def app(tmp_path, channel):
    from backend.app import create_app
    a = create_app(make_settings(tmp_path), alert_channels=[channel])
    for u, r in (("admin1", "admin"), ("doc1", "doctor"), ("aud1", "auditor"), ("dev1", "device")):
        add_user(a, u, r)
    return a


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture
def headers(client):
    return {r: login(client, u) for u, r in (("admin1", "admin"), ("doc1", "doctor"), ("aud1", "auditor"),
                                               ("dev1", "device"))}


def window(base=20.0, step=0.0, n=20, start=None, loss=0.0):
    start = start or datetime(2026, 10, 20, tzinfo=timezone.utc)
    out = []
    for k in range(n):
        avg = base + step * k
        out.append({"timestamp": (start + timedelta(seconds=240 * k)).isoformat(), "rtt_avg_ms": avg,
                    "rtt_min_ms": avg * 0.95, "rtt_max_ms": avg * 1.05, "jitter_ms": avg * 0.02, "loss_pct": loss})
    return out


def event(event_id="test-evt-0001", device="TEST-DEV-1", criticality=None, vitals=None, base=20.0, step=0.0,
          cost=0.3, **kw):
    e = {"event_id": event_id, "device_id": device, "source": "test", "network_window": window(base, step),
         "cloud_cost_index": cost}
    if vitals is not None:
        e["vitals"] = vitals
    if criticality is not None or vitals is None:
        e["criticality"] = 2.0 if criticality is None else criticality
    e.update(kw)
    return e
