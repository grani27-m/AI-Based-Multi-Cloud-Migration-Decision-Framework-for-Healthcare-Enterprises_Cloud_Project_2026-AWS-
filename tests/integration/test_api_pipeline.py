"""End-to-end API tests: ingest -> real predictor -> real AHP -> execution -> DB -> audit -> alerts -> dashboard."""

from __future__ import annotations

from tests.conftest import event


def test_health_and_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/ready").json()
    assert r["database"] is True


def test_full_pipeline_routine_reading_goes_to_cloud(client, headers, app):
    r = client.post("/api/v1/events", json=event(criticality=1.0, base=20), headers=headers["device"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "completed" and body["duplicate"] is False
    # Charles's predictor actually ran (model or explicit fallback, never a silent fake)
    assert body["prediction"]["method"] in ("lstm", "persistence_fallback")
    if app.state.predictor.model_loaded:
        assert body["prediction"]["method"] == "lstm"
    # Tanmay's engine produced an explainable decision
    d = body["decision"]
    assert d["destination"] == "CLOUD" and d["reason"] == "ahp_decision"
    assert d["cloud_score"] > d["edge_score"] and abs(sum(d["weights"].values()) - 1) < 1e-9
    # Rani's executor persisted the outcome
    assert body["execution"]["status"] == "success" and body["execution"]["final_destination"] == "CLOUD"
    assert body["execution"]["output_ref"].startswith("local-s3://")
    assert body["alerts"] == []
    # stored and retrievable
    got = client.get(f"/api/v1/events/{body['event_id']}", headers=headers["auditor"]).json()
    assert got["decision"]["destination"] == "CLOUD" and len(got["network_window"]) == 20


def test_emergency_vitals_trigger_override_alert_and_delivery_log(client, headers, channel):
    crit_vitals = {"hr": 140, "resp": 30, "spo2": 88}  # partial NEWS2 = 3+3+3 = 9 -> criticality 10
    r = client.post("/api/v1/events", json=event("test-evt-emerg", vitals=crit_vitals), headers=headers["doctor"])
    b = r.json()
    assert b["criticality"]["score"] == 10.0 and "partial_news2" in b["criticality"]["method"]
    assert b["decision"]["destination"] == "EDGE" and b["decision"]["reason"] == "override_critical_patient"
    assert b["execution"]["final_destination"] == "EDGE"
    assert [a["kind"] for a in b["alerts"]] == ["emergency_override"]
    alerts = client.get("/api/v1/alerts", headers=headers["doctor"]).json()["items"]
    assert alerts[0]["status"] == "delivered" and alerts[0]["deliveries"][0]["status"] == "sent"
    assert len(channel.sent) == 1 and "EMERGENCY" in channel.sent[0]


def test_degraded_network_triggers_network_veto(client, headers):
    r = client.post(
        "/api/v1/events", json=event("test-evt-veto", criticality=1.0, base=300, step=15), headers=headers["device"]
    )
    b = r.json()
    if b["prediction"]["predicted_rtt_ms"] >= 300:
        assert b["decision"]["reason"] == "network_degradation_veto" and b["decision"]["destination"] == "EDGE"
        assert b["alerts"][0]["kind"] == "network_veto"
        alerts = client.get("/api/v1/alerts?severity=WARNING", headers=headers["admin"]).json()["items"]
        assert alerts[0]["status"] == "not_notified"  # WARNING is recorded, not pushed, by default policy


def test_idempotent_duplicate_event_is_not_reprocessed(client, headers):
    e = event("test-evt-dup", criticality=3.0)
    first = client.post("/api/v1/events", json=e, headers=headers["device"])
    second = client.post("/api/v1/events", json=e, headers=headers["device"])
    assert first.status_code == 201 and second.status_code == 200 and second.json()["duplicate"] is True
    assert client.get("/api/v1/events?source=test", headers=headers["admin"]).json()["total"] == 1
    execs = client.get("/api/v1/executions", headers=headers["admin"]).json()
    assert execs["total"] == 1


def test_cloud_failure_falls_back_to_edge(client, headers):
    r = client.post(
        "/api/v1/events",
        json=event("test-evt-cfail", criticality=0.5, simulate_failure="cloud"),
        headers=headers["device"],
    )
    ex = r.json()["execution"]
    assert ex["requested_destination"] == "CLOUD" and ex["status"] == "fallback_success"
    assert ex["final_destination"] == "EDGE" and ex["attempts"] == 4  # 3 cloud tries + 1 edge


def test_edge_failure_is_reported_and_alerted(client, headers):
    r = client.post(
        "/api/v1/events",
        json=event("test-evt-efail", criticality=9.5, simulate_failure="both"),
        headers=headers["device"],
    )
    b = r.json()
    assert b["status"] == "failed" and b["execution"]["status"] == "failed"
    assert {a["kind"] for a in b["alerts"]} == {"emergency_override", "execution_failure"}


def test_invalid_payloads_rejected_without_partial_writes(client, headers):
    bad = event("test-evt-bad", criticality=11)  # out of range
    assert client.post("/api/v1/events", json=bad, headers=headers["device"]).status_code == 422
    short = event("test-evt-short")
    short["network_window"] = short["network_window"][:5]
    assert client.post("/api/v1/events", json=short, headers=headers["device"]).status_code == 422
    unordered = event("test-evt-order")
    unordered["network_window"][3], unordered["network_window"][4] = (
        unordered["network_window"][4],
        unordered["network_window"][3],
    )
    assert client.post("/api/v1/events", json=unordered, headers=headers["device"]).status_code == 422
    both = event("test-evt-both", criticality=2, vitals={"hr": 80, "resp": 15, "spo2": 98})
    assert client.post("/api/v1/events", json=both, headers=headers["device"]).status_code == 422
    live_fault = event("test-evt-live", source="live", simulate_failure="cloud")
    assert client.post("/api/v1/events", json=live_fault, headers=headers["device"]).status_code == 422
    assert client.get("/api/v1/events", headers=headers["admin"]).json()["total"] == 0


def test_oversized_body_rejected(client, headers):
    big = event("test-evt-big")
    big["provenance"] = {"x": "a" * 300_000}
    r = client.post("/api/v1/events", json=big, headers=headers["device"])
    assert r.status_code == 413


def test_dashboard_counts_reconcile_with_records(client, headers):
    client.post("/api/v1/events", json=event("t-1", criticality=1.0), headers=headers["device"])
    client.post("/api/v1/events", json=event("t-2", criticality=9.6), headers=headers["device"])
    client.post(
        "/api/v1/events", json=event("t-3", criticality=0.2, simulate_failure="both"), headers=headers["device"]
    )
    s = client.get("/api/v1/dashboard/summary", headers=headers["auditor"]).json()
    assert s["events"]["total"] == 3
    assert s["decisions"]["total"] == 3
    assert sum(s["decisions"]["by_reason"].values()) == s["decisions"]["total"]
    assert s["decisions"]["edge"]["count"] + s["decisions"]["cloud"]["count"] == 3
    assert all(v is True for k, v in s["reconciliation"].items() if isinstance(v, bool))
    events = client.get("/api/v1/events", headers=headers["auditor"]).json()
    assert events["total"] == s["events"]["total"]
    # alerts: triggered vs delivered are different numbers by construction
    assert s["alerts"]["triggered"] == 2 and s["alerts"]["delivered"] == 2  # t-2 emergency + t-3 exec failure
    ts = client.get("/api/v1/dashboard/timeseries", headers=headers["doctor"]).json()["items"]
    assert len(ts) == 3


def test_audit_chain_records_pipeline_and_verifies(client, headers):
    client.post("/api/v1/events", json=event("t-audit", criticality=4.0), headers=headers["device"])
    a = client.get("/api/v1/audit", headers=headers["auditor"]).json()
    actions = {i["action"] for i in a["items"]}
    assert {"login", "event_received", "event_processed"} <= actions
    v = client.get("/api/v1/audit/verify", headers=headers["auditor"]).json()
    assert v["valid"] is True and v["checked"] == a["total"] and len(v["head_hash"]) == 64


def test_demo_run_simulated_and_replay(client, headers):
    r = client.post(
        "/api/v1/demo/run",
        json={"mode": "simulate", "count": 25, "scenario": "mixed", "seed": 3},
        headers=headers["admin"],
    )
    assert r.status_code == 200 and r.json()["processed"] == 25
    r2 = client.post("/api/v1/demo/run", json={"mode": "replay", "count": 10, "seed": 3}, headers=headers["admin"])
    assert r2.status_code == 200 and r2.json()["processed"] == 10
    again = client.post("/api/v1/demo/run", json={"mode": "replay", "count": 10, "seed": 3}, headers=headers["admin"])
    assert again.json()["duplicates"] == 10  # deterministic ids -> idempotent replays
    s = client.get("/api/v1/dashboard/summary?source=replay", headers=headers["admin"]).json()
    assert s["events"]["total"] == 10
