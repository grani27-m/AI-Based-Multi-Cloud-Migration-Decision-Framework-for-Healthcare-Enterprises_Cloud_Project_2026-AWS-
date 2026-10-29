"""Rani: audit tamper detection, alert delivery accounting, execution adapters and retries."""

from __future__ import annotations

import json

from sqlalchemy import select, update

from backend.audit import GENESIS, verify_chain, write_audit
from backend.db import Database, run_migrations
from backend.models import Alert, AuditLog
from backend.services.alerts import dispatch_alert
from src.execution.adapters import ExecutionError, Executor, LocalCloudObjectStoreAdapter, LocalEdgeAdapter
from tests.conftest import FakeChannel, event, make_settings


def _db(tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    run_migrations(url)
    return Database(url)


def _chain(db, n=5):
    with db.session() as s:
        for i in range(n):
            write_audit(s, "tester", "action", f"res/{i}", {"i": i})


def test_intact_chain_verifies(tmp_path):
    db = _db(tmp_path)
    _chain(db)
    with db.session() as s:
        v = verify_chain(s)
        first = s.execute(select(AuditLog).order_by(AuditLog.id)).scalars().first()
    assert v["valid"] and v["checked"] == 5 and first.prev_hash == GENESIS


def test_edited_row_detected(tmp_path):
    db = _db(tmp_path)
    _chain(db)
    with db.session() as s:
        s.execute(update(AuditLog).where(AuditLog.id == 3).values(detail={"i": 999}))
    with db.session() as s:
        v = verify_chain(s)
    assert not v["valid"] and v["first_broken_id"] == 3 and "edited" in v["problem"]


def test_deleted_row_detected(tmp_path):
    db = _db(tmp_path)
    _chain(db)
    with db.session() as s:
        s.delete(s.get(AuditLog, 2))
    with db.session() as s:
        v = verify_chain(s)
    assert not v["valid"] and v["first_broken_id"] == 3


def test_reordered_rows_detected(tmp_path):
    db = _db(tmp_path)
    _chain(db)
    keys = ("ts", "actor", "action", "resource", "detail", "prev_hash", "hash")
    with db.session() as s:  # swap the full contents of rows 2 and 4 (an attacker reordering history)
        r2, r4 = s.get(AuditLog, 2), s.get(AuditLog, 4)
        a = {k: getattr(r2, k) for k in keys}
        b = {k: getattr(r4, k) for k in keys}
        r4.hash = "t" * 64
        s.flush()
        for k in keys:
            setattr(r2, k, b[k])
        s.flush()
        for k in keys:
            setattr(r4, k, a[k])
    with db.session() as s:
        v = verify_chain(s)
    assert not v["valid"] and v["first_broken_id"] == 2


def test_inserted_forged_row_detected(tmp_path):
    db = _db(tmp_path)
    _chain(db, 3)
    with db.session() as s:
        last = s.get(AuditLog, 3)
        s.add(
            AuditLog(
                ts=last.ts,
                actor="attacker",
                action="forged",
                resource="x",
                detail={},
                prev_hash=last.hash,
                hash="f" * 64,
            )
        )
    with db.session() as s:
        assert verify_chain(s)["first_broken_id"] == 4


def test_audit_detail_never_contains_vitals_or_tokens(client, headers):
    client.post(
        "/api/v1/events", json=event("phi-1", vitals={"hr": 77, "resp": 14, "spo2": 98}), headers=headers["device"]
    )
    dump = json.dumps(client.get("/api/v1/audit?limit=1000", headers=headers["admin"]).json())
    assert "spo2" not in dump and "Bearer" not in dump and "password" not in dump


# ---------------- alerts ----------------


def _alert_app(tmp_path, channels):
    from backend.app import create_app
    from tests.conftest import add_user, login
    from fastapi.testclient import TestClient

    app = create_app(make_settings(tmp_path), alert_channels=channels)
    add_user(app, "dev9", "device")
    c = TestClient(app)
    c.post("/api/v1/events", json=event("alert-evt", criticality=9.9), headers=login(c, "dev9"))
    with app.state.db.session() as s:
        return app, s.execute(select(Alert)).scalars().all()


def test_alert_retries_then_delivers(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.services.alerts.time.sleep", lambda s: None)
    flaky = FakeChannel("flaky", fail_times=2)
    app, alerts = _alert_app(tmp_path, [flaky])
    assert alerts[0].status == "delivered"
    with app.state.db.session() as s:
        d = s.get(Alert, alerts[0].id).deliveries
        assert [x.status for x in d] == ["failed", "failed", "sent"] and "timeout" in d[0].detail


def test_alert_all_channels_fail(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.services.alerts.time.sleep", lambda s: None)
    _, alerts = _alert_app(tmp_path, [FakeChannel("down", fail_times=99)])
    assert alerts[0].status == "failed"


def test_alert_partial_delivery(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.services.alerts.time.sleep", lambda s: None)
    _, alerts = _alert_app(tmp_path, [FakeChannel("ok"), FakeChannel("down", fail_times=99)])
    assert alerts[0].status == "partially_delivered"


def test_alert_not_configured_is_not_counted_as_sent(tmp_path):
    app, alerts = _alert_app(tmp_path, [FakeChannel("tg", configured=False)])
    assert alerts[0].status == "not_configured"
    with app.state.db.session() as s:
        assert [d.status for d in s.get(Alert, alerts[0].id).deliveries] == ["skipped"]


def test_dispatch_is_idempotent(tmp_path):
    ch = FakeChannel("ok")
    app, alerts = _alert_app(tmp_path, [ch])
    again = dispatch_alert(app.state.db.session, app.state.settings, alerts[0].id, channels=[ch])
    assert again == "delivered" and len(ch.sent) == 1


def test_secrets_are_sanitised_in_delivery_log(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.services.alerts.time.sleep", lambda s: None)

    class Leaky(FakeChannel):
        def send(self, alert):
            raise RuntimeError("POST https://api.telegram.org/botSECRET-TOKEN-123/sendMessage failed")

    from backend.app import create_app

    s = make_settings(tmp_path)
    s.telegram_bot_token = "SECRET-TOKEN-123"
    from tests.conftest import add_user, login
    from fastapi.testclient import TestClient

    app = create_app(s, alert_channels=[Leaky("leaky")])
    add_user(app, "dev9", "device")
    c = TestClient(app)
    c.post("/api/v1/events", json=event("leak-evt", criticality=9.9), headers=login(c, "dev9"))
    with app.state.db.session() as db:
        details = [d.detail for a in db.execute(select(Alert)).scalars() for d in a.deliveries]
    assert details and all("SECRET-TOKEN-123" not in d for d in details)


# ---------------- execution ----------------


def _payload(**kw):
    return {
        "event_id": "e1",
        "device_id": "D1",
        "criticality": 3.0,
        "network_window": [{"rtt_avg_ms": 10.0}],
        "predicted_rtt_ms": 11.0,
        "reason": "ahp_decision",
        **kw,
    }


def test_edge_and_cloud_adapters_write_records(tmp_path):
    ex = Executor(LocalEdgeAdapter(tmp_path), LocalCloudObjectStoreAdapter(tmp_path), backoff_s=0)
    e = ex.execute("EDGE", _payload())
    c = ex.execute("CLOUD", _payload(event_id="e2"))
    assert e.status == "success" and e.adapter == "local-edge-simulator" and e.attempts == 1
    assert c.status == "success" and c.output_ref.startswith("local-s3://") and c.final_destination == "CLOUD"
    assert any((tmp_path / "edge_buffer").iterdir()) and list((tmp_path / "cloud_objects").rglob("e2.json"))


def test_transient_failure_retried(tmp_path):
    class Flaky(LocalCloudObjectStoreAdapter):
        n = 0

        def execute(self, payload):
            Flaky.n += 1
            if Flaky.n < 3:
                raise ExecutionError("transient")
            return super().execute(payload)

    out = Executor(LocalEdgeAdapter(tmp_path), Flaky(tmp_path), backoff_s=0).execute("CLOUD", _payload())
    assert out.status == "success" and out.attempts == 3 and [a["ok"] for a in out.attempt_log] == [False, False, True]


def test_cloud_failure_falls_back_edge_failure_does_not_go_to_cloud(tmp_path):
    ex = Executor(LocalEdgeAdapter(tmp_path), LocalCloudObjectStoreAdapter(tmp_path), backoff_s=0)
    fb = ex.execute("CLOUD", _payload(simulate_failure="cloud"))
    assert fb.status == "fallback_success" and fb.final_destination == "EDGE"
    ef = ex.execute("EDGE", _payload(simulate_failure="edge"))
    assert ef.status == "failed" and ef.final_destination is None and ef.attempts == 3
    assert all(a["destination"] == "EDGE" for a in ef.attempt_log)


def test_unknown_destination_rejected(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        Executor(LocalEdgeAdapter(tmp_path), LocalCloudObjectStoreAdapter(tmp_path)).execute("MARS", _payload())
