"""
Package-level tests: run Rani's numbered scripts end-to-end against a TEMPORARY database and a real
uvicorn process (never touches runtime/app.db or your .env secrets).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

PKG = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rani_pkg")
    port = _free_port()
    e = dict(os.environ)
    e.update(
        ENVIRONMENT="test",
        SECRET_KEY="pkg-test-" + "k" * 48,
        DATABASE_URL=f"sqlite:///{tmp / 'pkg.db'}",
        RUNTIME_DIR=str(tmp / "runtime"),
        BOOTSTRAP_ADMIN_USERNAME="admin",
        BOOTSTRAP_ADMIN_PASSWORD="Test-Admin-pw-1",
        DOCTOR_PASSWORD="Test-Doctor-pw-1",
        DEVICE_PASSWORD="Test-Device-pw-1",
        STREAM_USER="sim-device",
        PASSWORD_HASH_ITERATIONS="1000",
        ALERT_MOCK_FILE=str(tmp / "mock_alerts.jsonl"),
        TELEGRAM_BOT_TOKEN="", SMTP_HOST="", ALERT_WEBHOOK_URL="",
        API_URL=f"http://127.0.0.1:{port}",
        PYTHONIOENCODING="utf-8",
    )
    return {"env": e, "tmp": tmp, "port": port}


def run(script, env, *args, timeout=240):
    return subprocess.run([sys.executable, str(PKG / script), *args], cwd=PKG, env=env["env"], capture_output=True,
                          text=True, timeout=timeout)


@pytest.fixture(scope="module")
def server(env):
    r = run("01_initialize_database.py", env)
    assert r.returncode == 0, r.stdout + r.stderr
    p = subprocess.Popen([sys.executable, str(PKG / "02_start_backend.py"), "--port", str(env["port"])], cwd=PKG,
                         env=env["env"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = env["env"]["API_URL"]
    for _ in range(120):
        try:
            if httpx.get(base + "/ready", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        p.kill()
        pytest.fail("backend did not start")
    yield base
    p.terminate()
    p.wait(timeout=20)


def test_initialize_database_is_idempotent(env):
    a = run("01_initialize_database.py", env)
    b = run("01_initialize_database.py", env)
    assert a.returncode == 0 and b.returncode == 0, a.stderr + b.stderr
    assert "exists - password reset" in b.stdout
    assert "telemetry_events" in b.stdout and "audit_log" in b.stdout


def test_execution_demo_all_checks_pass(env, server):
    r = run("03_run_execution_demo.py", env, "--replay", "4")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert "[FAIL]" not in r.stdout
    assert "replay (real data)" in r.stdout and "simulated emergency" in r.stdout


def test_mock_alerts_are_labelled_and_never_delivered(env, server):
    base = server
    tok = httpx.post(base + "/api/v1/auth/login", json={"username": "admin", "password": "Test-Admin-pw-1"}).json()["access_token"]
    s = httpx.get(base + "/api/v1/dashboard/summary", headers={"Authorization": f"Bearer {tok}"}).json()["alerts"]
    assert s["delivered"] == 0  # no real channel configured in this test
    assert s["mock_delivered"] >= 1
    lines = (env["tmp"] / "mock_alerts.jsonl").read_text().splitlines()
    assert lines and all(json.loads(x)["MOCK"] is True for x in lines)


def test_audit_inspection_and_tamper_detection(env, server):
    r = run("04_inspect_audit_logs.py", env, "--limit", "5")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "hash chain: VALID" in r.stdout and "execution history" in r.stdout
    t = run("04_inspect_audit_logs.py", env, "--tamper-demo")
    assert t.returncode == 0, t.stdout + t.stderr
    assert "content hash mismatch" in t.stdout and "Tamper detected" in t.stdout
    assert not list((env["tmp"]).glob("tamper_demo_copy.db*"))  # copy cleaned up
    r2 = run("04_inspect_audit_logs.py", env, "--limit", "1")
    assert "hash chain: VALID" in r2.stdout  # original database untouched


def test_persistence_across_restart(env, server):
    r = run("06_persistence_check.py", env, "--port", str(_free_port()))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[FAIL]" not in r.stdout and "6/6 checks passed" in r.stdout


def test_dashboard_renders_from_live_api(env, server, monkeypatch):
    from streamlit.testing.v1 import AppTest

    for k, v in env["env"].items():
        monkeypatch.setenv(k, v)
    at = AppTest.from_file(str(PKG / "05_dashboard.py"), default_timeout=120).run()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.tabs) == 6
    labels = {m.label: m.value for m in at.metric}
    assert int(labels["Events stored"]) >= 8
    assert any("Hash chain VALID" in s.value for s in at.success)
    stage = next(s for s in at.selectbox if s.label == "…or choose a stage")
    stage.select("execution").run()
    next(b for b in at.button if b.label == "Show stage details").click().run()
    assert not at.exception
    assert any(m.value.startswith("#### Execution:") for m in at.markdown)
