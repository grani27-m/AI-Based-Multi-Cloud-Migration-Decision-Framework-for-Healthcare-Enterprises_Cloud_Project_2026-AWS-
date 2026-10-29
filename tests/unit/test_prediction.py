"""Charles's prediction pipeline: parsing, features, windows/splits, model inference, service contract."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.prediction.dataset import make_windows
from src.prediction.features import FEATURES, WINDOW, Scaler, fill_missing, transform_raw
from src.prediction.model import NumpyLSTM
from src.prediction.predict_service import LatencyPredictor, PredictionInputError, classify_risk
from src.prediction.ripe_parser import parse_result
from tests.conftest import window

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models" / "latency_lstm"
HAS_MODEL = (MODEL_DIR / "weights.npz").exists()

PING = {
    "type": "ping",
    "msm_id": 1001,
    "prb_id": 1,
    "timestamp": 1792541012,
    "sent": 3,
    "rcvd": 3,
    "min": 13.39,
    "max": 14.22,
    "avg": 13.86,
    "result": [{"rtt": 14.22}, {"rtt": 13.39}, {"rtt": 13.97}],
}


def test_parse_valid_ping_and_derived_fields():
    r = parse_result(PING)
    assert r["invalid_reason"] == "" and r["rtt_avg_ms"] == 13.86 and r["loss_pct"] == 0.0
    assert math.isclose(r["jitter_ms"], (abs(13.39 - 14.22) + abs(13.97 - 13.39)) / 2)


def test_parse_total_loss_keeps_row_without_rtt():
    r = parse_result({**PING, "rcvd": 0, "avg": -1, "min": -1, "max": -1, "result": [{"x": "*"}] * 3})
    assert r["invalid_reason"] == "" and r["loss_pct"] == 100.0 and math.isnan(r["rtt_avg_ms"])


@pytest.mark.parametrize(
    "patch,reason",
    [
        ({"sent": 0}, "bad_counts"),
        ({"rcvd": 5}, "bad_counts"),
        ({"avg": 99999}, "bad_rtt"),
        ({"min": 20}, "bad_rtt"),
        ({"error": "x"}, "probe_error"),
        ({"type": "traceroute"}, "not_ping"),
    ],
)
def test_parse_flags_invalid(patch, reason):
    assert parse_result({**PING, **patch})["invalid_reason"] == reason


def test_no_bandwidth_or_signal_strength_invented():
    assert "bandwidth_mbps" not in FEATURES and "signal_strength_dbm" not in FEATURES
    assert "bandwidth_mbps" not in parse_result(PING)


def test_fill_missing_forward_then_back():
    a = np.array([[np.nan, 1.0], [2.0, np.nan], [np.nan, 3.0]])
    assert fill_missing(a).tolist() == [[2.0, 1.0], [2.0, 1.0], [2.0, 3.0]]


def test_transform_shape_and_time_features():
    raw = np.full((WINDOW, 5), 10.0)
    x = transform_raw(raw, np.arange(WINDOW) * 240 + 6 * 3600)
    assert x.shape == (WINDOW, len(FEATURES))
    assert math.isclose(x[0, 0], math.log1p(10.0)) and math.isclose(x[0, 5], 1.0, abs_tol=1e-9)  # 06:00 -> sin=1


def _toy_frame(n=200, gap_at=None):
    ts = np.arange(n) * 240 + 1_700_000_000
    if gap_at:
        ts[gap_at:] += 3600
    df = pd.DataFrame(
        {
            "msm_id": 1001,
            "prb_id": 1,
            "timestamp": ts,
            "rtt_avg_ms": 20 + np.sin(np.arange(n)),
            "rtt_min_ms": 19.0,
            "rtt_max_ms": 22.0,
            "jitter_ms": 0.5,
            "loss_pct": 0.0,
            "group": "access_network",
            "series_id": "1001-1",
        }
    )
    df["rtt_min_ms"] = df["rtt_avg_ms"] - 1
    gap = df["timestamp"].diff()
    df["segment"] = (gap.isna() | (gap > 360)).cumsum()
    return df


def test_windows_never_cross_split_or_gap():
    df = _toy_frame(300, gap_at=150)
    t = df.timestamp.to_numpy()
    w = make_windows(df, (int(t[100]), int(t[220])))
    for s in ("train", "val", "test"):
        assert w[f"X_{s}"].shape[1:] == (WINDOW, len(FEATURES))
    assert w["ts_train"].max() < t[100]
    assert w["ts_test"].min() >= t[220]
    total = sum(len(w[f"y_{s}"]) for s in ("train", "val", "test"))
    assert total < 300 - 2 * WINDOW  # boundary and gap windows dropped


def test_scaler_roundtrip():
    x = np.random.default_rng(0).normal(5, 2, (100, 7))
    y = np.random.default_rng(1).normal(3, 1, 100)
    s = Scaler.fit(x, y)
    s2 = Scaler.from_dict(json.loads(json.dumps(s.to_dict())))
    assert np.allclose(s2.y_inverse(s2.y(y)), y, atol=1e-5)


def test_risk_classes():
    assert [classify_risk(v) for v in (10, 74.99, 75, 149.9, 150)] == ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH"]


def test_fallback_is_explicitly_labelled(tmp_path):
    p = LatencyPredictor.load(tmp_path)  # empty dir -> no artifacts
    r = p.predict(window(base=42.0))
    assert not p.model_loaded and r.method == "persistence_fallback" and r.model_version == "none"
    assert r.predicted_rtt_ms == 42.0  # = last observed RTT, NOT last*1.1


@pytest.mark.parametrize(
    "mutate,msg",
    [
        (lambda w: w[:19], "exactly 20"),
        (lambda w: list(reversed(w)), "strictly increasing"),
        (lambda w: [{**o, "loss_pct": 101} for o in w], "loss_pct"),
        (lambda w: [{**o, "rtt_avg_ms": None} for o in w], "required"),
    ],
)
def test_service_rejects_bad_windows(tmp_path, mutate, msg):
    with pytest.raises(PredictionInputError, match=msg):
        LatencyPredictor.load(tmp_path).predict(mutate(window()))


@pytest.mark.skipif(not HAS_MODEL, reason="trained model artifacts not present")
def test_trained_model_loads_and_predicts_sensibly():
    p = LatencyPredictor.load(MODEL_DIR)
    assert p.model_loaded and p.model_version.startswith("lstm-")
    meta = json.loads((MODEL_DIR / "preprocessing.json").read_text())
    assert meta["features"] == FEATURES and meta["window"] == WINDOW
    r = p.predict(window(base=30.0))
    assert r.method == "lstm" and 10 < r.predicted_rtt_ms < 90  # stable 30 ms path -> about 30 ms


@pytest.mark.skipif(not HAS_MODEL, reason="trained model artifacts not present")
def test_numpy_inference_matches_keras():
    tf = pytest.importorskip("tensorflow")
    model = tf.keras.models.load_model(MODEL_DIR / "model.keras")
    x = np.random.default_rng(0).normal(0, 1, (16, WINDOW, len(FEATURES))).astype(np.float32)
    k = model.predict(x, verbose=0)[:, 0]
    n = NumpyLSTM(MODEL_DIR / "weights.npz").predict(x)
    assert np.max(np.abs(k - n)) < 1e-4
