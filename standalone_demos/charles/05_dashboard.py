"""
05 - Charles's interactive latency analytics dashboard.

    streamlit run 05_dashboard.py            # opens http://localhost:8501

Everything shown is computed from the REAL files in this package (raw-derived clean table,
metadata, trained model). Predictions are produced live by the shipped model (numpy inference).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from demo_common import META, MODEL_DIR, RESULTS, load_clean, mae_rmse, measurements_meta, predict_series, probes_meta, read_json, splits

st.set_page_config(page_title="Charles - RIPE Atlas latency prediction", layout="wide")
SPLIT_COLORS = {"train": "rgba(37,99,235,0.07)", "validation": "rgba(234,179,8,0.12)", "test": "rgba(22,163,74,0.10)"}


@st.cache_data(show_spinner="Loading 753k real RIPE Atlas rounds...")
def data() -> pd.DataFrame:
    return load_clean()


@st.cache_data(show_spinner="Running the trained LSTM on this series...")
def preds(series_id: str) -> pd.DataFrame:
    return predict_series(data()[lambda d: d.series_id == series_id])


try:
    df = data()
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()

probes = probes_meta()
msms = {m["id"]: m for m in measurements_meta() if not m.get("rejected")}
quality = read_json(META / "ripe_atlas_quality.json")
sp = splits()
metrics = read_json(RESULTS / "model" / "metrics.json")
model_meta = read_json(MODEL_DIR / "preprocessing.json")

st.title("Network-latency prediction on real RIPE Atlas data")
st.caption("Charles Jehanabad (24BIT0522) · data source: RIPE Atlas built-in pings (REAL) · model "
           f"{model_meta['model_version']} · all figures computed from files in this folder")

k = st.columns(6)
k[0].metric("Raw results", f"{quality['rows_raw']:,}")
k[1].metric("Clean rows", f"{quality['rows_clean']:,}")
k[2].metric("Probes × targets", quality["series"])
k[3].metric("Test windows", f"{metrics['test_windows']:,}")
k[4].metric("LSTM test MAE", f"{metrics['overall']['lstm']['mae_ms']:.3f} ms")
k[5].metric("Persistence MAE", f"{metrics['overall']['persistence']['mae_ms']:.3f} ms",
            delta=f"{-metrics['overall']['lstm']['mae_skill_vs_persistence'] * 100:.1f}% for LSTM", delta_color="inverse")

with st.sidebar:
    st.header("Select data")
    msm_id = st.selectbox("Measurement", list(msms), format_func=lambda m: f"{m} → {msms[m]['target']}")
    available = sorted(df.loc[df.msm_id == msm_id, "prb_id"].unique())
    pmeta = probes.set_index("id")
    prb = st.selectbox("Probe", available,
                       format_func=lambda p: f"{p} · {pmeta.loc[p, 'group']} · {str(pmeta.loc[p, 'description'])[:28]}")
    sid = f"{msm_id}-{prb}"
    st.caption(f"Splits (UTC): train {sp['train'][0][:10]}→{sp['train'][1][:10]}, "
               f"validation →{sp['val'][1][:10]}, test →{sp['test'][1][:10]}")

tabs = st.tabs(["Readings", "Prediction vs actual", "Model evaluation", "Relationship graph", "Data sources & quality"])
series = df[df.series_id == sid]

with tabs[0]:
    st.subheader(f"Series {sid}: {len(series):,} real ping rounds")
    if series.empty:
        st.info("No rows for this selection.")
    else:
        fig = go.Figure()
        for name, (a, b) in {"train": sp["train"], "validation": sp["val"], "test": sp["test"]}.items():
            fig.add_vrect(x0=a, x1=b, fillcolor=SPLIT_COLORS[name], line_width=0, annotation_text=name,
                          annotation_position="top left")
        fig.add_trace(go.Scattergl(x=series.time_utc, y=series.rtt_max_ms, name="max RTT", line=dict(width=0.5, color="#bbb")))
        fig.add_trace(go.Scattergl(x=series.time_utc, y=series.rtt_avg_ms, name="avg RTT", line=dict(width=1, color="#1f77b4")))
        fig.add_trace(go.Scattergl(x=series.time_utc, y=series.rtt_min_ms, name="min RTT", line=dict(width=0.5, color="#888")))
        fig.update_layout(height=380, yaxis_title="RTT (ms)", margin=dict(t=30, b=10), legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")
        loss = series.set_index("time_utc")["loss_pct"].resample("1h").mean()
        fig2 = go.Figure(go.Bar(x=loss.index, y=loss.values, marker_color="#d62728"))
        fig2.update_layout(height=200, yaxis_title="packet loss % (hourly mean)", margin=dict(t=10, b=10))
        st.plotly_chart(fig2, width="stretch")
        c = st.columns(4)
        c[0].metric("median RTT", f"{series.rtt_avg_ms.median():.2f} ms")
        c[1].metric("p99 RTT", f"{series.rtt_avg_ms.quantile(0.99):.1f} ms")
        c[2].metric("rounds with 100 % loss", f"{int((series.rcvd == 0).sum()):,}")
        c[3].metric("mean jitter", f"{series.jitter_ms.mean():.2f} ms")
        with st.expander("Raw rows (first 500)"):
            st.dataframe(series.drop(columns=["time_utc"]).head(500), width="stretch")

with tabs[1]:
    p = preds(sid)
    if p.empty:
        st.info("Not enough contiguous rounds for 20-step windows in this series.")
    else:
        part = st.radio("Split", ["test", "validation", "train"], horizontal=True,
                        help="Test = held out (never used for training or model selection).")
        q = p[p.split == part]
        hours = st.slider("Hours to plot", 6, 72, 48)
        q_plot = q[q.time_utc <= q.time_utc.min() + pd.Timedelta(hours=hours)] if len(q) else q
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=q_plot.time_utc, y=q_plot.actual_ms, name="actual", line=dict(color="#222", width=1.2)))
        fig.add_trace(go.Scatter(x=q_plot.time_utc, y=q_plot.lstm_ms, name="LSTM forecast", line=dict(color="#1f77b4", width=1.2)))
        fig.add_trace(go.Scatter(x=q_plot.time_utc, y=q_plot.persistence_ms, name="persistence baseline",
                                 line=dict(color="#ff7f0e", width=1, dash="dot")))
        fig.update_layout(height=420, yaxis_title="next-round RTT (ms)", margin=dict(t=20), legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")
        rows = []
        for split_name in ("train", "validation", "test"):
            r = p[p.split == split_name]
            if len(r):
                lm, lr = mae_rmse(r.actual_ms, r.lstm_ms)
                pm, pr = mae_rmse(r.actual_ms, r.persistence_ms)
                rows.append({"split": split_name, "windows": len(r), "LSTM MAE": lm, "persistence MAE": pm,
                             "LSTM RMSE": lr, "persistence RMSE": pr})
        st.markdown(f"**This series only** ({sid}) — predictions computed now by the shipped model:")
        st.dataframe(pd.DataFrame(rows).round(3), width="stretch", hide_index=True)

with tabs[2]:
    st.subheader(f"Held-out test set: {metrics['test_windows']:,} windows, {metrics['test_period_utc'][0][:10]} → {metrics['test_period_utc'][1][:10]}")
    names = {"lstm": "LSTM", "persistence": "Persistence", "mean20": "Mean of 20", "ewma": "EWMA α=0.3", "ridge": "Ridge"}
    tbl = pd.DataFrame([{"method": names[k2], "MAE ms": v["mae_ms"], "RMSE ms": v["rmse_ms"],
                         "MAE skill vs persistence": v["mae_skill_vs_persistence"], "risk-class accuracy": v["risk_class_accuracy"]}
                        for k2, v in metrics["overall"].items()])
    st.dataframe(tbl.round(4), width="stretch", hide_index=True)
    st.write(f"Objective 1 (LSTM beats persistence on MAE **and** RMSE): **{'MET' if metrics['objective_1_met'] else 'NOT MET'}**. "
             "EWMA and ridge have a slightly lower RMSE than the LSTM; spikes ≥ 300 ms (2 in the test period) are not predicted by any method.")
    g = pd.DataFrame([{"group": grp, **{names[k2]: v["mae_ms"] for k2, v in r.items()}} for grp, r in metrics["by_group"].items()])
    st.markdown("MAE by probe group (ms)")
    st.dataframe(g.round(3), width="stretch", hide_index=True)
    hist = read_json(MODEL_DIR / "training_history.json")
    fig = go.Figure([go.Scatter(y=hist["loss"], x=list(range(1, len(hist["loss"]) + 1)), name="train"),
                     go.Scatter(y=hist["val_loss"], x=list(range(1, len(hist["val_loss"]) + 1)), name="validation")])
    fig.update_layout(height=280, xaxis_title="epoch", yaxis_title=f"{model_meta['training']['loss']} loss", margin=dict(t=20))
    st.plotly_chart(fig, width="stretch")
    log = read_json(RESULTS / "model" / "experiments" / "experiment_log.json")
    st.markdown("Model selection (validation only): " + log["selection_rule"])
    st.dataframe(pd.DataFrame(log["runs"]), width="stretch", hide_index=True)

with tabs[3]:
    st.markdown("**Measurements → targets → probes → networks.** Click a node to see its real metadata and connected records.")
    stats = df.groupby(["msm_id", "prb_id"]).agg(rows=("timestamp", "size"), median_rtt=("rtt_avg_ms", "median"),
                                                 loss_rounds=("rcvd", lambda s: int((s == 0).sum()))).reset_index()
    nodes, edges = {}, []
    groups = sorted(probes.group.unique())
    for i, (mid, m) in enumerate(msms.items()):
        nodes[f"msm:{mid}"] = dict(kind="measurement", x=0, y=1 - i * 0.6, label=f"msm {mid}", meta=m)
        nodes[f"tgt:{m['target']}"] = dict(kind="target", x=-1, y=1 - i * 0.6, label=m["target"], meta={"target_ip": m.get("target_ip")})
        edges.append((f"msm:{mid}", f"tgt:{m['target']}", "pings"))
    asns = sorted(probes.asn_v4.unique())
    for j, (_, pr) in enumerate(probes.sort_values(["group", "asn_v4"]).iterrows()):
        pid = int(pr["id"])
        y = 1.3 - j * (2.4 / max(len(probes) - 1, 1))
        nodes[f"prb:{pid}"] = dict(kind="probe", x=1.2, y=y, label=str(pid), meta=pr.to_dict())
        for _, r in stats[stats.prb_id == pid].iterrows():
            edges.append((f"msm:{int(r.msm_id)}", f"prb:{pid}", f"{int(r.rows):,} rows"))
        edges.append((f"prb:{pid}", f"asn:{pr.asn_v4}", "in network"))
    for j, a in enumerate(asns):
        sub = probes[probes.asn_v4 == a]
        nodes[f"asn:{a}"] = dict(kind="network", x=2.4, y=1.3 - j * (2.4 / max(len(asns) - 1, 1)), label=f"AS{a}",
                                 meta={"asn": int(a), "group": ", ".join(sorted(sub.group.unique())), "probes": sub.id.tolist()})
    for j, gname in enumerate(groups):
        nodes[f"grp:{gname}"] = dict(kind="group", x=3.4, y=0.7 - j * 1.0, label=gname, meta={"probes": int((probes.group == gname).sum())})
    for a in asns:
        for gname in probes[probes.asn_v4 == a].group.unique():
            edges.append((f"asn:{a}", f"grp:{gname}", "group"))
    sel_key = st.session_state.get("graph_sel")
    connected = {b if a == sel_key else a for a, b, _ in edges if sel_key in (a, b)} if sel_key else set()
    ex, ey = [], []
    hx, hy = [], []
    for a, b, _ in edges:
        tx, ty = ((hx, hy) if sel_key in (a, b) else (ex, ey))
        tx += [nodes[a]["x"], nodes[b]["x"], None]
        ty += [nodes[a]["y"], nodes[b]["y"], None]
    colors = {"measurement": "#2563eb", "target": "#7c3aed", "probe": "#16a34a", "network": "#ea580c", "group": "#64748b"}
    keys = list(nodes)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color="#d4d4d8", width=1), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=hx, y=hy, mode="lines", line=dict(color="#dc2626", width=2.5), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=[nodes[k2]["x"] for k2 in keys], y=[nodes[k2]["y"] for k2 in keys], mode="markers+text",
        text=[nodes[k2]["label"] for k2 in keys], textposition="middle right", customdata=keys,
        marker=dict(size=[22 if k2 == sel_key else 16 if k2 in connected else 12 for k2 in keys],
                    color=[colors[nodes[k2]["kind"]] for k2 in keys], line=dict(width=1, color="white")),
        hovertext=[f"{nodes[k2]['kind']}: {nodes[k2]['label']}" for k2 in keys], hoverinfo="text", showlegend=False))
    fig.update_layout(height=640, xaxis=dict(visible=False, range=[-1.6, 4.2]), yaxis=dict(visible=False),
                      margin=dict(t=10, b=10, l=10, r=10), clickmode="event+select", dragmode=False)
    ev = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key="graph")
    pts = (ev or {}).get("selection", {}).get("points", []) if isinstance(ev, dict) else getattr(getattr(ev, "selection", None), "points", [])
    if pts:
        new = pts[0].get("customdata")
        new = new[0] if isinstance(new, list) else new
        if new and new != sel_key:
            st.session_state["graph_sel"] = new
            st.rerun()
    pick = st.selectbox("…or pick a node", keys, index=keys.index(sel_key) if sel_key in keys else 0,
                        format_func=lambda k2: f"{nodes[k2]['kind']}: {nodes[k2]['label']}")
    if pick != sel_key and st.button("Show this node"):
        st.session_state["graph_sel"] = pick
        st.rerun()
    if sel_key:
        n = nodes[sel_key]
        st.markdown(f"### {n['kind']}: {n['label']}")
        c1, c2 = st.columns(2)
        c1.json({k2: (str(v) if not isinstance(v, (int, float, str, list, dict, type(None))) else v) for k2, v in n["meta"].items()})
        rel = [{"connected": nodes[b if a == sel_key else a]["label"], "kind": nodes[b if a == sel_key else a]["kind"], "relation": lab}
               for a, b, lab in edges if sel_key in (a, b)]
        c2.dataframe(pd.DataFrame(rel), width="stretch", hide_index=True)
        if n["kind"] == "probe":
            pid = int(sel_key.split(":")[1])
            c2.dataframe(stats[stats.prb_id == pid].round(2), width="stretch", hide_index=True)

with tabs[4]:
    st.markdown("**Real data sources** (no synthetic data in this package)")
    st.dataframe(pd.DataFrame([{k2: m.get(k2) for k2 in ("id", "type", "target", "target_ip", "interval", "rejected", "reason")}
                               for m in measurements_meta()]), width="stretch", hide_index=True)
    st.dataframe(probes[["id", "group", "asn_v4", "description", "status", "total_uptime"]].astype(str),
                 width="stretch", hide_index=True)
    st.markdown("**Cleaning counts** (`dataset/metadata/ripe_atlas_quality.json`)")
    st.json({k2: quality[k2] for k2 in ("rows_raw", "invalid_by_reason", "rows_after_validity", "duplicates_removed", "rows_clean",
                                        "rows_total_loss", "rows_jitter_undefined", "rows_rtt_ge_150ms", "rows_rtt_ge_300ms", "time_range_utc")})
    st.markdown("**Missing values in the processed table**")
    st.dataframe(df.drop(columns=["time_utc"]).isna().sum().rename("missing").to_frame().T, width="stretch")
    st.markdown("**Chronological windows**")
    st.json(sp["windows"])
