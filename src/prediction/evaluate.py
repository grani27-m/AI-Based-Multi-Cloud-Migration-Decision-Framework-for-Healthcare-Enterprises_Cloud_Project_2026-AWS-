"""
src/prediction/evaluate.py  —  Owner: Charles
==============================================
Honest held-out evaluation of the trained LSTM against simple baselines on the
SAME chronological test windows (never seen in training or early stopping).

    python -m src.prediction.evaluate

Baselines
    persistence  next RTT = last observed RTT              (the report's required baseline)
    mean20       next RTT = mean RTT of the 20-step window
    ewma         exponentially weighted mean, alpha = 0.3   (named in report §8.4)
    ridge        linear regression on the scaled flattened window (fitted on train)

Outputs: results/model/metrics.json, results/model/*.png
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from src.prediction.features import FEATURES, Scaler, last_log_rtt, target_from_model
from src.prediction.model import NumpyLSTM

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "dataset" / "processed" / "windows_w20.npz"
MODEL_DIR = ROOT / "models" / "latency_lstm"
OUT = ROOT / "results" / "model"
RTT_COL = FEATURES.index("rtt_avg_ms")
log = logging.getLogger("evaluate")


def risk_class(ms: np.ndarray) -> np.ndarray:
    return np.where(ms < 75, 0, np.where(ms < 150, 1, 2))  # LOW / MEDIUM / HIGH (report thresholds)


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    e = p - y
    return {"mae_ms": float(np.mean(np.abs(e))), "rmse_ms": float(np.sqrt(np.mean(e ** 2))),
            "median_ae_ms": float(np.median(np.abs(e))),
            "risk_class_accuracy": float(np.mean(risk_class(y) == risk_class(p))), "n": int(len(y))}


def spike_scores(y: np.ndarray, p: np.ndarray, thr: float) -> dict:
    t, h = y >= thr, p >= thr
    tp = int((t & h).sum())
    return {"threshold_ms": thr, "actual_events": int(t.sum()), "predicted_events": int(h.sum()), "true_positives": tp,
            "precision": (tp / h.sum()) if h.sum() else None, "recall": (tp / t.sum()) if t.sum() else None}


def predict_lstm(X: np.ndarray, scaler: Scaler, target_mode: str, batch: int = 8192) -> np.ndarray:
    """Use the SAME numpy inference path as the API."""
    net = NumpyLSTM(MODEL_DIR / "weights.npz")
    out = scaler.y_inverse(np.concatenate([net.predict(scaler.x(X[i:i + batch])) for i in range(0, len(X), batch)]))
    if target_mode == "residual":
        out = out + last_log_rtt(X)
    return target_from_model(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    d = np.load(WINDOWS)
    meta = json.loads((MODEL_DIR / "preprocessing.json").read_text())
    scaler = Scaler.from_dict(meta["scaler"])
    X, y = d["X_test"], d["y_ms_test"]
    rtt_win = np.expm1(X[:, :, RTT_COL].astype(np.float64))  # carried-forward RTTs of the window

    preds = {"lstm": predict_lstm(X, scaler, meta.get("target_mode", "level")), "persistence": d["last_ms_test"].astype(np.float64),
             "mean20": rtt_win.mean(1)}
    w = 0.3 * (0.7 ** np.arange(rtt_win.shape[1])[::-1])
    preds["ewma"] = (rtt_win * w).sum(1) / w.sum()
    from sklearn.linear_model import Ridge
    Xtr = d["X_train"]
    # ridge baseline gets the same residual target as the LSTM (fair comparison)
    resid = meta.get("target_mode") == "residual"
    ytr = d["y_train"] - (last_log_rtt(Xtr) if resid else 0)
    ridge = Ridge(alpha=1.0).fit(scaler.x(Xtr).reshape(len(Xtr), -1), ytr)
    pr = ridge.predict(scaler.x(X).reshape(len(X), -1)) + (last_log_rtt(X) if resid else 0)
    preds["ridge"] = target_from_model(pr)

    res = {"model_version": meta["model_version"], "test_windows": int(len(y)),
           "test_period_utc": json.loads((ROOT / "dataset/metadata/ripe_atlas_splits.json").read_text())["test"],
           "overall": {k: metrics(y, p) for k, p in preds.items()}, "by_group": {}, "spikes": {}}
    for g in np.unique(d["group_test"]):
        m = d["group_test"] == g
        res["by_group"][str(g)] = {k: metrics(y[m], p[m]) for k, p in preds.items()}
    for thr in (150.0, 300.0):
        res["spikes"][str(int(thr))] = {k: spike_scores(y, p, thr) for k, p in preds.items()}
    pers = res["overall"]["persistence"]
    for k in preds:
        o = res["overall"][k]
        o["mae_skill_vs_persistence"] = 1 - o["mae_ms"] / pers["mae_ms"]
        o["rmse_skill_vs_persistence"] = 1 - o["rmse_ms"] / pers["rmse_ms"]
    res["objective_1_met"] = bool(res["overall"]["lstm"]["mae_ms"] < pers["mae_ms"]
                                  and res["overall"]["lstm"]["rmse_ms"] < pers["rmse_ms"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(res, indent=2))
    _plots(d, preds, y)
    for k, v in res["overall"].items():
        log.info("%-12s MAE %.3f ms  RMSE %.3f ms  skill(MAE) %+.3f", k, v["mae_ms"], v["rmse_ms"],
                 v["mae_skill_vs_persistence"])
    log.info("objective 1 (LSTM beats persistence on MAE and RMSE): %s", res["objective_1_met"])
    return 0


def _plots(d, preds, y) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    hist = json.loads((MODEL_DIR / "training_history.json").read_text())
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(hist["loss"], label="train loss")
    ax.plot(hist["val_loss"], label="validation loss")
    ax.set_xlabel("epoch")
    ax.set_ylabel("MSE (scaled log-RTT)")
    ax.set_title("LSTM training history (RIPE Atlas, real data)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "training_history.png", dpi=130)
    plt.close(fig)

    names = d["series_names"]
    sid = d["series_test"]
    # pick the access-network series with the highest RTT variance for an informative plot
    best, best_var = None, -1
    for s in np.unique(sid):
        m = sid == s
        if d["group_test"][m][0] == "access_network" and m.sum() > 600 and y[m].std() > best_var:
            best, best_var = s, y[m].std()
    m = np.flatnonzero(sid == best)[:720]  # ~2 days at 240 s
    fig, ax = plt.subplots(figsize=(11, 4))
    t = (d["ts_test"][m] - d["ts_test"][m][0]) / 3600
    ax.plot(t, y[m], lw=1, label="actual", color="#222")
    ax.plot(t, preds["lstm"][m], lw=1, label="LSTM", color="#1f77b4")
    ax.plot(t, preds["persistence"][m], lw=0.8, label="persistence", color="#ff7f0e", alpha=0.7)
    ax.set_xlabel("hours into test period")
    ax.set_ylabel("RTT (ms)")
    ax.set_title(f"Held-out test: predicted vs actual, series {names[best]}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "pred_vs_actual.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ks = list(preds)
    mae = [np.mean(np.abs(preds[k] - y)) for k in ks]
    ax.bar(ks, mae, color=["#1f77b4" if k == "lstm" else "#999" for k in ks])
    ax.set_ylabel("MAE (ms), test set")
    ax.set_title("LSTM vs baselines on identical held-out windows")
    for i, v in enumerate(mae):
        ax.text(i, v, f"{v:.2f}", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(OUT / "baseline_comparison.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
