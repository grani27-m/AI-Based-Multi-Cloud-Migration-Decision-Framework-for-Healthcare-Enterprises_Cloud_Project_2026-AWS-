"""
05 - Operations dashboard for Rani's backend. Every number on this page comes from the RUNNING local API
     (start `python 02_start_backend.py` first); nothing is computed or invented in the dashboard itself.

    streamlit run 05_dashboard.py          # http://localhost:8501

Tabs: System · Send events · Request flow (clickable graph per stored event) · Executions · Alerts · Audit log
"""

from __future__ import annotations

import json
import time

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from demo_common import api_url, load_env

env = load_env()
st.set_page_config(page_title="Rani - execution, backend & audit", layout="wide")
BASE = st.sidebar.text_input("API URL", api_url())


def call(method: str, path: str, token: str | None = None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = httpx.request(method, BASE + path, headers=h, timeout=60, **kw)
    except httpx.HTTPError as e:
        return None, str(e)
    try:
        body = r.json()
    except ValueError:
        body = r.text
    return r.status_code, body


def token_for(user: str, pw: str) -> str | None:
    code, body = call("POST", "/api/v1/auth/login", json={"username": user, "password": pw})
    return body["access_token"] if code == 200 else None


# ---------------------------------------------------------------- sidebar: connection + login
code, health = call("GET", "/health")
if code != 200:
    st.title("Execution, backend & audit — Rani Gupta (24BIT0543)")
    st.error(f"Backend not reachable at {BASE}: {health}.  Start it in another terminal:  `python 02_start_backend.py`")
    st.stop()
st.sidebar.success(f"API online · version {health.get('version', '?')}")
user = st.sidebar.text_input("Username", env.get("BOOTSTRAP_ADMIN_USERNAME") or "admin")
pw = st.sidebar.text_input("Password", env.get("BOOTSTRAP_ADMIN_PASSWORD", ""), type="password",
                           help="pre-filled from your local .env (created by 00_setup_env.py)")
if "tok" not in st.session_state or st.session_state.get("tok_user") != user or st.sidebar.button("Log in again"):
    st.session_state["tok"], st.session_state["tok_user"] = token_for(user, pw), user
TOK = st.session_state["tok"]
if not TOK:
    st.sidebar.error("login failed")
    st.stop()
code, me = call("GET", "/api/v1/auth/me", TOK)
st.sidebar.write(f"logged in as **{me.get('username')}** · role **{me.get('role')}**")
st.sidebar.caption("Roles: admin (all) · doctor (records, ack) · auditor (records, audit) · device (send events only)")

st.title("Execution, backend & audit — Rani Gupta (24BIT0543)")
st.caption("FastAPI + SQLAlchemy + Alembic, persistent database, JWT roles, execution adapters with retry/fallback, "
           "hash-chained audit log, alert delivery log. Data shown live from " + BASE)

t_sys, t_send, t_flow, t_exec, t_alert, t_audit = st.tabs(
    ["System", "Send events", "Request flow", "Executions", "Alerts", "Audit log"])

# ---------------------------------------------------------------- System
with t_sys:
    _, ready = call("GET", "/ready")
    c, summ = call("GET", "/api/v1/dashboard/summary", TOK)
    if c != 200:
        st.warning(f"/dashboard/summary: HTTP {c} (role {me.get('role')} may lack records:read)")
    else:
        ev, de, al = summ.get("events", {}), summ.get("decisions", {}), summ.get("alerts", {})
        m = st.columns(6)
        m[0].metric("Events stored", ev.get("total", 0))
        m[1].metric("EDGE decisions", de.get("edge", {}).get("count", 0), f"{de.get('edge', {}).get('pct', 0)} %", delta_color="off")
        m[2].metric("CLOUD decisions", de.get("cloud", {}).get("count", 0), f"{de.get('cloud', {}).get('pct', 0)} %", delta_color="off")
        m[3].metric("Alerts triggered", al.get("triggered", 0))
        m[4].metric("Really delivered", al.get("delivered", 0))
        m[5].metric("Mock-delivered", al.get("mock_delivered", 0), help="local mock file only - nobody was notified")
        a, b = st.columns(2)
        a.markdown("**Decisions by reason**")
        a.bar_chart(pd.Series(de.get("by_reason", {}), name="count"))
        b.markdown("**Executions by status**")
        b.bar_chart(pd.Series(summ.get("executions", {}).get("by_status", {}), name="count"))
        with st.expander("raw /api/v1/dashboard/summary"):
            st.json(summ)
    st.markdown("**Readiness** (`GET /ready`)")
    st.json(ready)
    c, info = call("GET", "/api/v1/system/info", TOK)
    if c == 200:
        x = st.columns(3)
        x[0].markdown("**Database**")
        x[0].json(info.get("database"))
        x[1].markdown("**Execution adapters**")
        x[1].json(info.get("execution"))
        x[2].markdown("**Alert channels configured**")
        x[2].json(info.get("alert_channels_configured"))
        st.markdown("**Model served by the API**")
        st.json(info.get("model"), expanded=False)

# ---------------------------------------------------------------- Send events
with t_send:
    st.markdown("Events are sent with the **device** account exactly as a gateway would (`POST /api/v1/events`).")
    dev_tok = token_for(env.get("STREAM_USER") or "sim-device", env.get("DEVICE_PASSWORD", ""))
    if not dev_tok:
        st.error("device login failed - run 01_initialize_database.py")
    else:
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("Real replay")
            st.caption("RIPE Atlas held-out test windows + PhysioNet BIDMC vitals (real data)")
            n = st.number_input("events", 1, 100, 10)
            if st.button("Send replay events", type="primary"):
                from data_ingestion.replay import build_replay_events

                out = []
                for e in build_replay_events(int(n), seed=int(time.time()) % 100000):
                    c, b = call("POST", "/api/v1/events", dev_tok, json=e)
                    out.append(b if c in (200, 201) else {"event_id": e["event_id"], "status": f"HTTP {c}"})
                st.session_state["sent"] = out
        with col_r:
            st.subheader("Labelled simulated scenario")
            st.caption("synthetic inputs, real pipeline")
            sc = st.selectbox("scenario", ["normal", "degraded", "emergency", "failure (cloud down)", "both adapters down"])
            if st.button("Send scenario event"):
                from data_ingestion.simulator import build_simulated_events

                base_sc = sc.split(" ")[0] if sc[0] in "nde" else "normal"
                e = build_simulated_events(1, scenario=base_sc, seed=int(time.time() * 1000) % 10**7)[0]
                if sc.startswith("failure"):
                    e["simulate_failure"] = "cloud"
                if sc.startswith("both"):
                    e["simulate_failure"] = "both"
                c, b = call("POST", "/api/v1/events", dev_tok, json=e)
                st.session_state["sent"] = [b if c in (200, 201) else {"event_id": e["event_id"], "status": f"HTTP {c}: {b}"}]
            st.subheader("Invalid input")
            if st.button("Send an invalid event (SpO2 = 140 %)"):
                from data_ingestion.simulator import build_simulated_events

                e = build_simulated_events(1, seed=int(time.time()) % 10**6)[0]
                e["vitals"]["spo2"] = 140
                c, b = call("POST", "/api/v1/events", dev_tok, json=e)
                st.write(f"HTTP **{c}** - rejected, nothing stored")
                st.json(b, expanded=False)
        if st.session_state.get("sent"):
            rows = [{"event_id": b.get("event_id"), "device": b.get("device_id"), "status": b.get("status"),
                     "criticality": (b.get("criticality") or {}).get("score"),
                     "predicted_rtt_ms": (b.get("prediction") or {}).get("predicted_rtt_ms"),
                     "destination": (b.get("decision") or {}).get("destination"),
                     "reason": (b.get("decision") or {}).get("reason"),
                     "execution": (b.get("execution") or {}).get("status"),
                     "final": (b.get("execution") or {}).get("final_destination"),
                     "alerts": len(b.get("alerts") or []), "duplicate": b.get("duplicate")}
                    for b in st.session_state["sent"]]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            st.caption("Open the **Request flow** tab to follow one of these events through every stage.")

# ---------------------------------------------------------------- Request flow
with t_flow:
    c, evs = call("GET", "/api/v1/events?limit=200", TOK)
    if c != 200 or not evs.get("items"):
        st.info("No events stored yet - use the Send events tab or `python 03_run_execution_demo.py`.")
    else:
        ids = [f"{i['event_id']}  [{i['source']}] {i['destination']} / {i['reason']}" for i in evs["items"]]
        pick = st.selectbox(f"Stored event ({evs['total']} total, newest first)", ids)
        eid = pick.split("  ")[0]
        _, d = call("GET", f"/api/v1/events/{eid}", TOK)
        _, aud = call("GET", "/api/v1/audit?limit=1000", TOK)
        alert_ids = {f"alert/{a['id']}" for a in d.get("alerts") or []}
        audit_rows = [a for a in (aud.get("items", []) if isinstance(aud, dict) else [])
                      if a["resource"] == f"event/{eid}" or a["resource"] in alert_ids]
        p, dec, ex = d.get("prediction") or {}, d.get("decision") or {}, d.get("execution") or {}
        nodes = {
            "device": dict(x=0, y=1, label=f"Device {d['device_id']}", kind="input",
                           info={"device_id": d["device_id"], "source": d["source"], "observed_at": d["observed_at"],
                                 "provenance": d.get("provenance")}),
            "api": dict(x=1, y=1, label="API: auth + validation", kind="api",
                        info={"endpoint": "POST /api/v1/events", "received_at": d["received_at"],
                              "window_rounds": len(d.get("network_window") or []), "status": d["status"], "error": d.get("error")}),
            "telemetry": dict(x=2, y=2, label="telemetry_events row", kind="db",
                              info={"network_window_last3": (d.get("network_window") or [])[-3:],
                                    "criticality": d["criticality"], "cloud_cost_index": d["cloud_cost_index"]}),
            "prediction": dict(x=2, y=0, label=f"LSTM → {p.get('predicted_rtt_ms', 'n/a') if not p else round(p['predicted_rtt_ms'], 1)} ms",
                               kind="model", info=p or {"note": "no prediction"}),
            "decision": dict(x=3, y=1, label=f"AHP + vetoes → {dec.get('destination')}", kind="decision",
                             info={k: dec.get(k) for k in ("destination", "reason", "veto", "edge_score", "cloud_score",
                                                           "weights", "normalised", "explanation")}),
            "execution": dict(x=4, y=1, label=f"Execution: {ex.get('status')} ({ex.get('final_destination')})", kind="exec",
                              info=ex or {"note": "no execution"}),
            "alerts": dict(x=5, y=2, label=f"Alerts: {len(d.get('alerts') or [])}", kind="alert",
                           info={"alerts": d.get("alerts")}),
            "audit": dict(x=5, y=0, label=f"Audit entries: {len(audit_rows)}", kind="audit",
                          info={"entries": [{k: a[k] for k in ("id", "ts", "actor", "action", "resource", "hash", "prev_hash")}
                                            for a in sorted(audit_rows, key=lambda a: a["id"])]}),
        }
        edges = [("device", "api"), ("api", "telemetry"), ("api", "prediction"), ("telemetry", "decision"),
                 ("prediction", "decision"), ("decision", "execution"), ("execution", "alerts"), ("execution", "audit"),
                 ("decision", "alerts")]
        sel = st.session_state.get("rf_sel")
        fig = go.Figure()
        for a, b in edges:
            hot = sel in (a, b)
            fig.add_trace(go.Scatter(x=[nodes[a]["x"], nodes[b]["x"]], y=[nodes[a]["y"], nodes[b]["y"]], mode="lines",
                                     line=dict(width=4 if hot else 2, color="#dc2626" if hot else "#cbd5e1"),
                                     hoverinfo="skip", showlegend=False))
        colors = {"input": "#64748b", "api": "#7c3aed", "db": "#0369a1", "model": "#2563eb", "decision": "#0f766e",
                  "exec": "#16a34a" if ex.get("status") == "success" else "#b45309", "alert": "#dc2626", "audit": "#334155"}
        keys = list(nodes)
        fig.add_trace(go.Scatter(x=[nodes[k]["x"] for k in keys], y=[nodes[k]["y"] for k in keys], mode="markers+text",
                                 text=[nodes[k]["label"] for k in keys], textposition="top center", customdata=keys,
                                 marker=dict(size=[30 if k == sel else 20 for k in keys],
                                             color=[colors[nodes[k]["kind"]] for k in keys]),
                                 hoverinfo="text", hovertext=[nodes[k]["kind"] for k in keys], showlegend=False))
        fig.update_layout(height=420, xaxis=dict(visible=False, range=[-0.6, 5.8]), yaxis=dict(visible=False, range=[-0.6, 2.7]),
                          margin=dict(t=10, b=10), dragmode=False)
        evsel = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key="rf")
        pts = []
        if evsel is not None:
            selobj = getattr(evsel, "selection", None)
            pts = getattr(selobj, "points", None) or (evsel.get("selection", {}).get("points", []) if isinstance(evsel, dict) else [])
        if pts:
            cd = pts[0].get("customdata")
            cd = cd[0] if isinstance(cd, list) else cd
            if cd and cd != sel:
                st.session_state["rf_sel"] = cd
                st.rerun()
        pick_node = st.selectbox("…or choose a stage", keys, index=keys.index(sel) if sel in keys else 0)
        if st.button("Show stage details"):
            st.session_state["rf_sel"] = sel = pick_node
            st.rerun()
        sel = sel or "decision"
        st.markdown(f"#### {nodes[sel]['label']}")
        st.json(json.loads(json.dumps(nodes[sel]["info"], default=str)))
        if d.get("network_window"):
            w = pd.DataFrame(d["network_window"])
            w["timestamp"] = pd.to_datetime(w["timestamp"])
            f2 = go.Figure()
            f2.add_trace(go.Scatter(x=w["timestamp"], y=w["rtt_avg_ms"], name="observed RTT (20 rounds)", mode="lines+markers"))
            if p.get("predicted_rtt_ms") is not None:
                f2.add_trace(go.Scatter(x=[w["timestamp"].iloc[-1] + pd.Timedelta(seconds=p.get("horizon_s") or 240)],
                                        y=[p["predicted_rtt_ms"]], name="LSTM forecast (next round)",
                                        mode="markers", marker=dict(size=13, symbol="star")))
            f2.update_layout(height=280, yaxis_title="RTT ms", margin=dict(t=20, b=10))
            st.plotly_chart(f2, width="stretch")

# ---------------------------------------------------------------- Executions
with t_exec:
    c, exs = call("GET", "/api/v1/executions?limit=500", TOK)
    if c == 200 and exs["items"]:
        df = pd.DataFrame(exs["items"])
        a, b = st.columns([1, 2])
        a.markdown("**By status**")
        a.dataframe(df["status"].value_counts(), width="stretch")
        b.markdown("**Requested → final destination**")
        b.dataframe(pd.crosstab(df["requested_destination"], df["final_destination"].fillna("none")), width="stretch")
        st.caption("Adapters are LOCAL stand-ins (local-edge-simulator, local-cloud-object-store) unless CLOUD_ADAPTER=s3.")
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info(f"no executions (HTTP {c})")

# ---------------------------------------------------------------- Alerts
with t_alert:
    c, als = call("GET", "/api/v1/alerts?limit=500", TOK)
    if c == 200 and als["items"]:
        df = pd.DataFrame([{k: v for k, v in a.items() if k != "deliveries"} | {"attempts": len(a["deliveries"])}
                           for a in als["items"]])
        st.caption("`mock_delivered` = written only to the local mock file (ALERT_MOCK_FILE); **nobody was notified**. "
                   "`delivered` appears only when a real channel (Telegram, e-mail, webhook, SNS) succeeded.")
        st.dataframe(df, width="stretch", hide_index=True)
        aid = st.selectbox("delivery attempts for alert", [a["id"] for a in als["items"]])
        st.dataframe(pd.DataFrame(next(a for a in als["items"] if a["id"] == aid)["deliveries"]), width="stretch", hide_index=True)
    else:
        st.info(f"no alerts (HTTP {c})")

# ---------------------------------------------------------------- Audit
with t_audit:
    c, v = call("GET", "/api/v1/audit/verify", TOK)
    if c != 200:
        st.warning(f"HTTP {c}: role {me.get('role')} cannot read the audit log (audit:read = admin, auditor)")
    else:
        (st.success if v["valid"] else st.error)(
            f"Hash chain {'VALID' if v['valid'] else 'BROKEN'} - {v['checked']} entries checked"
            + (f", head {v['head_hash'][:20]}…" if v["valid"] else f"; first broken id {v['first_broken_id']}: {v['problem']}"))
        _, aud = call("GET", "/api/v1/audit?limit=300", TOK)
        df = pd.DataFrame(aud["items"])
        act = st.multiselect("actions", sorted(df["action"].unique()))
        if act:
            df = df[df["action"].isin(act)]
        df["detail"] = df["detail"].map(lambda x: json.dumps(x)[:120])
        st.dataframe(df[["id", "ts", "actor", "action", "resource", "detail", "prev_hash", "hash"]], width="stretch", hide_index=True)
        st.caption("Each entry stores SHA-256(prev_hash, ts, actor, action, resource, detail). Editing, deleting or reordering "
                   "any row breaks verification - try `python 04_inspect_audit_logs.py --tamper-demo`.")
