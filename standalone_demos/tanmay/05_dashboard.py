"""
05 - Tanmay's interactive decision dashboard.

    streamlit run 05_dashboard.py          # http://localhost:8501

Every number is computed live by src/decision/* (the same code the integrated API uses).
Inputs come from the sliders, from cached pipeline events (data/sample_events.json, labelled), or
from the editable list of cloud candidates.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from demo_common import load
from src.decision.ahp import ahp_report
from src.decision.candidates import CloudCandidate, rank_candidates
from src.decision.criticality import criticality_from_vitals
from src.decision.router import DecisionInput, DecisionInputError, decide

st.set_page_config(page_title="Tanmay - AHP decision engine", layout="wide")
st.title("Explainable edge / multi-cloud routing with AHP")
st.caption("Tanmay Kapoor (24BIT0079) · two-stage engine: hard safety vetoes, then AHP-weighted scores · "
           "all results computed live by src/decision")

events = load("sample_events.json")
example = load("candidates_example.json")

with st.sidebar:
    st.header("Inputs")
    mode = st.radio("Input source", ["Manual", "Cached pipeline event"],
                    help="Cached events: real LSTM forecasts + real BIDMC criticality (replay) or simulated inputs.")
    ws = st.selectbox("Weight set", ["eigenvector", "report", "column_normalisation"],
                      format_func=lambda w: {"eigenvector": "Eigenvector (verified, default)", "report": "As printed in report",
                                             "column_normalisation": "Column normalisation (old code)"}[w])
    if mode == "Manual":
        use_vitals = st.checkbox("Derive criticality from vitals (partial NEWS2)")
        if use_vitals:
            hr = st.slider("Heart rate (bpm)", 30, 180, 95)
            rr = st.slider("Respiration (breaths/min)", 4, 40, 20)
            sp = st.slider("SpO₂ (%)", 80, 100, 95)
            c = criticality_from_vitals(hr, rr, sp)
            crit = c.score
            st.info(f"NEWS2 points {c.points} → aggregate {c.aggregate} → criticality **{crit}**")
        else:
            crit = st.slider("Patient criticality", 0.0, 10.0, 5.0, 0.1)
        no_fc = st.checkbox("Latency forecast unavailable")
        lat = None if no_fc else float(st.slider("Predicted latency (ms)", 0, 600, 80))
        cost = st.slider("Cloud cost index", 0.0, 1.0, 0.4, 0.01)
        label = "manual input"
    else:
        src = st.selectbox("Source", ["replay", "simulated"])
        pool = [e for e in events["events"] if e["source"] == src]
        e = st.selectbox("Event", pool, format_func=lambda x: f"{x['device_id']} · crit {x['criticality']} · "
                                                              f"{x['predicted_latency_ms']:.0f} ms · {x['recorded_reason']}")
        crit, lat, cost = e["criticality"], e["predicted_latency_ms"], e["cloud_cost_index"]
        label = f"cached event {e['event_id']} ({'REAL replay data' if src == 'replay' else 'SIMULATED'})"
        st.json({k: e[k] for k in ("criticality", "criticality_method", "vitals", "predicted_latency_ms", "prediction_method",
                                   "model_version", "cloud_cost_index", "recorded_destination", "recorded_reason")})

tab_dec, tab_multi, tab_ahp, tab_sens, tab_fix = st.tabs(
    ["Decision (EDGE vs CLOUD)", "Multi-cloud ranking", "AHP weights & consistency", "Sensitivity map", "Cached events"])

with tab_dec:
    try:
        r = decide(DecisionInput("dashboard", crit, lat, cost), weight_set_name=ws)
    except DecisionInputError as exc:
        st.error(f"Input rejected: {exc}")
        st.stop()
    st.caption(f"Input: {label}")
    c = st.columns(4)
    c[0].metric("Destination", r.destination)
    c[1].metric("Reason", r.reason.replace("_", " "))
    c[2].metric("EDGE score", "—" if r.edge_score is None else f"{r.edge_score:.4f}")
    c[3].metric("CLOUD score", "—" if r.cloud_score is None else f"{r.cloud_score:.4f}")
    st.success(r.explanation) if r.destination == "CLOUD" else st.warning(r.explanation)

    if r.veto == "none":
        st.markdown("**Normalisation and weighted contributions**")
        raw = {"criticality": crit, "latency": lat, "cost": cost}
        tbl = pd.DataFrame([{"criterion": k, "raw input": raw[k], "normalised": r.normalised[k], "weight": r.weights[k],
                             "EDGE contribution": r.contributions["edge"][k], "CLOUD contribution": r.contributions["cloud"][k]}
                            for k in r.weights])
        st.dataframe(tbl.round(4), width="stretch", hide_index=True)
        st.caption("EDGE = w_c·n_c² + w_l·n_l + w_k·n_k · CLOUD = w_c·(1−n_c)² + w_l·(1−n_l) + w_k·(1−n_k) · "
                   "n_c = criticality/10, n_l = min(latency/500, 1), n_k = cost")

    # ---- decision-flow graph: inputs -> criteria (weights) -> alternatives -> decision ----
    st.markdown("**Decision-flow graph** — click a node to see the numbers behind it.")
    crit_names = list(r.weights)
    nodes = {
        "in:criticality": dict(x=0, y=2, label=f"criticality = {crit}", kind="input"),
        "in:latency": dict(x=0, y=1, label=f"latency = {lat if lat is not None else 'n/a'} ms", kind="input"),
        "in:cost": dict(x=0, y=0, label=f"cost = {cost}", kind="input"),
        "veto": dict(x=1, y=3.0, label=f"Stage A vetoes: {r.veto}", kind="veto"),
        "alt:EDGE": dict(x=3, y=1.6, label=f"EDGE {r.edge_score if r.edge_score is not None else ''}", kind="alternative"),
        "alt:CLOUD": dict(x=3, y=0.4, label=f"CLOUD {r.cloud_score if r.cloud_score is not None else ''}", kind="alternative"),
        "decision": dict(x=4.2, y=1.0, label=f"→ {r.destination}", kind="decision"),
    }
    for i, k in enumerate(crit_names):
        nodes[f"crit:{k}"] = dict(x=1.8, y=2 - i, label=f"{k}  w={r.weights[k]:.3f}", kind="criterion")
    edges = [(f"in:{k}", f"crit:{k}", 1.5) for k in crit_names] + [(f"in:{k}", "veto", 0.8) for k in ("criticality", "latency")]
    if r.veto == "none":
        for k in crit_names:
            edges.append((f"crit:{k}", "alt:EDGE", 1 + 12 * r.contributions["edge"][k]))
            edges.append((f"crit:{k}", "alt:CLOUD", 1 + 12 * r.contributions["cloud"][k]))
        edges.append((f"alt:{r.destination}", "decision", 5))
    else:
        edges.append(("veto", "decision", 5))
    sel = st.session_state.get("flow_sel")
    fig = go.Figure()
    for a, b, wdt in edges:
        hot = sel in (a, b)
        fig.add_trace(go.Scatter(x=[nodes[a]["x"], nodes[b]["x"]], y=[nodes[a]["y"], nodes[b]["y"]], mode="lines",
                                 line=dict(width=wdt, color="#dc2626" if hot else "#cbd5e1"), hoverinfo="skip", showlegend=False))
    colors = {"input": "#64748b", "criterion": "#2563eb", "alternative": "#0f766e", "decision": "#16a34a", "veto": "#b45309"}
    keys = list(nodes)
    fig.add_trace(go.Scatter(x=[nodes[k]["x"] for k in keys], y=[nodes[k]["y"] for k in keys], mode="markers+text",
                             text=[nodes[k]["label"] for k in keys], textposition="top center", customdata=keys,
                             marker=dict(size=[26 if k == sel else 18 for k in keys], color=[colors[nodes[k]["kind"]] for k in keys]),
                             hoverinfo="text", hovertext=[nodes[k]["kind"] for k in keys], showlegend=False))
    fig.update_layout(height=430, xaxis=dict(visible=False, range=[-0.6, 4.9]), yaxis=dict(visible=False, range=[-0.5, 3.5]),
                      margin=dict(t=10, b=10), dragmode=False)
    evsel = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key="flow")
    pts = getattr(getattr(evsel, "selection", None), "points", None) or (evsel or {}).get("selection", {}).get("points", []) \
        if evsel is not None else []
    if pts:
        cd = pts[0].get("customdata")
        cd = cd[0] if isinstance(cd, list) else cd
        if cd and cd != sel:
            st.session_state["flow_sel"] = cd
            st.rerun()
    pick = st.selectbox("…or choose a node", keys, index=keys.index(sel) if sel in keys else 0)
    if st.button("Show node details"):
        st.session_state["flow_sel"] = pick
        st.rerun()
    if sel:
        kind = nodes[sel]["kind"]
        st.markdown(f"#### {nodes[sel]['label']}  ({kind})")
        if kind == "criterion":
            k = sel.split(":")[1]
            st.json({"weight": r.weights[k], "normalised_input": r.normalised.get(k),
                     "edge_contribution": r.contributions.get("edge", {}).get(k),
                     "cloud_contribution": r.contributions.get("cloud", {}).get(k)})
        elif kind == "alternative":
            side = sel.split(":")[1].lower()
            st.json({"score": r.edge_score if side == "edge" else r.cloud_score, "contributions": r.contributions.get(side)})
        elif kind == "veto":
            st.json({"veto": r.veto, "thresholds": r.thresholds})
        elif kind == "decision":
            st.json({"destination": r.destination, "reason": r.reason, "engine_version": r.engine_version, "explanation": r.explanation})
        else:
            st.json({"value": {"in:criticality": crit, "in:latency": lat, "in:cost": cost}[sel]})

with tab_multi:
    st.markdown("Rank the hospital **edge** against several **cloud destinations** (`src/decision/candidates.py`). "
                "Defaults are a HYPOTHETICAL example; edit the table. With one cloud this gives exactly the same result as the "
                "two-alternative engine (tested).")
    m_crit = st.slider("Criticality for ranking", 0.0, 10.0, float(example["criticality"]), 0.1, key="mcrit")
    table = st.data_editor(pd.DataFrame(example["clouds"]), num_rows="dynamic", width="stretch", key="clouds")
    try:
        clouds = [CloudCandidate(str(row["name"]), None if pd.isna(row["predicted_latency_ms"]) else float(row["predicted_latency_ms"]),
                                 float(row["cost_index"])) for _, row in table.iterrows() if str(row["name"]).strip()]
        rr_ = rank_candidates("dashboard", m_crit, clouds, weight_set_name=ws)
        st.subheader(f"→ {rr_.destination}")
        st.write(rr_.explanation)
        rk = pd.DataFrame([{"rank": i + 1, "candidate": s.name, "kind": s.kind, "admissible": s.admissible,
                            "score": s.score, "excluded because": s.excluded_reason} for i, s in enumerate(rr_.ranking)])
        st.dataframe(rk, width="stretch", hide_index=True)
        ok = [s for s in rr_.ranking if s.score is not None]
        fig = go.Figure(go.Bar(x=[s.name for s in ok], y=[s.score for s in ok],
                               marker_color=["#16a34a" if s.name == rr_.destination else "#94a3b8" for s in ok]))
        fig.update_layout(height=300, yaxis_title="AHP score", margin=dict(t=10))
        st.plotly_chart(fig, width="stretch")
    except (DecisionInputError, ValueError, KeyError) as exc:
        st.error(f"Input rejected: {exc}")

with tab_ahp:
    rep = ahp_report()
    st.markdown("Pairwise comparison matrix (Saaty scale)")
    st.dataframe(pd.DataFrame(rep["matrix"], index=["criticality", "latency", "cost"], columns=["criticality", "latency", "cost"]).round(4))
    st.dataframe(pd.DataFrame([
        {"method": "Principal eigenvector (used)", **rep["eigenvector"]["weights"], "CR": rep["eigenvector"]["cr_ri_0_58"]},
        {"method": "Column normalisation (old code)", **rep["column_normalisation"]["weights"], "CR": rep["column_normalisation"]["cr_ri_0_58"]},
        {"method": "Printed in report", **rep["reported"]["weights"], "CR": rep["reported"]["cr"]}]).round(4), width="stretch", hide_index=True)
    st.write(f"λmax = {rep['eigenvector']['lambda_max']:.4f}, CI = {rep['eigenvector']['ci']:.5f}, CR = {rep['eigenvector']['cr_ri_0_58']:.4f} "
             f"(RI 0.58) / {rep['eigenvector']['cr_ri_0_52']:.4f} (RI 0.52). {rep['note']}")

with tab_sens:
    st.markdown("Destination over a grid of criticality × predicted latency (fixed cost index). Red = EDGE, blue = CLOUD.")
    s_cost = st.slider("Cost index", 0.0, 1.0, 0.3, 0.05, key="scost")
    cs = np.round(np.arange(0, 10.01, 0.25), 2)
    ls = np.arange(0, 401, 10)
    z = [[1 if decide(DecisionInput("g", float(c_), float(l_), s_cost), weight_set_name=ws).destination == "EDGE" else 0 for l_ in ls] for c_ in cs]
    fig = go.Figure(go.Heatmap(z=z, x=ls, y=cs, colorscale=[[0, "#2563eb"], [1, "#dc2626"]], showscale=False))
    fig.add_vline(x=300, line_dash="dash", annotation_text="veto 300 ms")
    fig.add_hline(y=9, line_dash="dash", annotation_text="emergency 9.0")
    fig.update_layout(height=420, xaxis_title="predicted latency (ms)", yaxis_title="criticality", margin=dict(t=10))
    st.plotly_chart(fig, width="stretch")

with tab_fix:
    st.markdown(events["description"])
    rows = []
    for e in events["events"]:
        rr2 = decide(DecisionInput(e["device_id"], e["criticality"], e["predicted_latency_ms"], e["cloud_cost_index"]))
        rows.append({"source": e["source"], "device": e["device_id"], "criticality": e["criticality"],
                     "predicted ms": e["predicted_latency_ms"], "cost": e["cloud_cost_index"], "recomputed": rr2.destination,
                     "recorded by integrated system": e["recorded_destination"], "reason": rr2.reason,
                     "match": rr2.destination == e["recorded_destination"]})
    df = pd.DataFrame(rows)
    st.metric("Recomputed decisions matching the integrated system", f"{int(df.match.sum())}/{len(df)}")
    st.dataframe(df, width="stretch", hide_index=True)
