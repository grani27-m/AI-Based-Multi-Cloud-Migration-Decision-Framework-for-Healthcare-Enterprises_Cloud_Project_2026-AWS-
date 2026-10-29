"""Rani: migrations from an empty DB, schema/model parity, and persistence across an application restart."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from backend.app import create_app
from tests.conftest import FakeChannel, add_user, event, login, make_settings

ROOT = Path(__file__).resolve().parents[2]
TABLES = {
    "users",
    "devices",
    "telemetry_events",
    "predictions",
    "routing_decisions",
    "execution_records",
    "alerts",
    "alert_deliveries",
    "audit_log",
    "alembic_version",
}


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)


def test_migrations_upgrade_check_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    assert set(inspect(create_engine(url)).get_table_names()) == TABLES
    chk = _alembic(url, "check")  # models and migrations agree
    assert chk.returncode == 0, chk.stdout + chk.stderr
    down = _alembic(url, "downgrade", "base")
    assert down.returncode == 0 and set(inspect(create_engine(url)).get_table_names()) == {"alembic_version"}


def test_records_survive_application_restart(tmp_path):
    s = make_settings(tmp_path)
    app1 = create_app(s, alert_channels=[FakeChannel()])
    add_user(app1, "dev1", "device")
    add_user(app1, "aud1", "auditor")
    with TestClient(app1) as c:
        r = c.post("/api/v1/events", json=event("persist-1", criticality=9.5), headers=login(c, "dev1"))
        assert r.status_code == 201
    app1.state.db.dispose()
    del app1

    app2 = create_app(make_settings(tmp_path), alert_channels=[FakeChannel()])  # new process-equivalent
    with TestClient(app2) as c:
        h = login(c, "aud1")
        got = c.get("/api/v1/events/persist-1", headers=h)
        assert got.status_code == 200
        b = got.json()
        assert b["decision"]["reason"] == "override_critical_patient" and b["execution"]["status"] == "success"
        assert c.get("/api/v1/alerts", headers=h).json()["items"][0]["status"] == "delivered"
        assert c.get("/api/v1/audit/verify", headers=h).json()["valid"] is True
        dup = c.post("/api/v1/events", json=event("persist-1", criticality=9.5), headers=login(c, "dev1"))
        assert dup.status_code == 403 or dup.json().get("duplicate") is True
