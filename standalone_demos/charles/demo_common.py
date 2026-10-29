"""Helpers shared by Charles's numbered demo scripts and dashboard (package-only file, not exported)."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # make `src.*` importable when run from any directory
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CLEAN = ROOT / "dataset" / "processed" / "ripe_atlas_clean.csv.gz"
META = ROOT / "dataset" / "metadata"
MODEL_DIR = ROOT / "models" / "latency_lstm"
RESULTS = ROOT / "results"


def read_json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def splits() -> dict:
    return read_json(META / "ripe_atlas_splits.json")


def split_cutoffs() -> tuple[int, int]:
    s = splits()
    return (int(datetime.fromisoformat(s["val"][0]).timestamp()), int(datetime.fromisoformat(s["test"][0]).timestamp()))


def split_of(ts: np.ndarray) -> np.ndarray:
    t1, t2 = split_cutoffs()
    return np.where(ts < t1, "train", np.where(ts < t2, "validation", "test"))


def load_clean() -> pd.DataFrame:
    if not CLEAN.exists():
        raise FileNotFoundError(f"{CLEAN} missing - run: python 02_validate_and_preprocess.py")
    df = pd.read_csv(CLEAN)
    df["time_utc"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df


def probes_meta() -> pd.DataFrame:
    return pd.DataFrame(read_json(META / "ripe_atlas_probes.json")["probes"])


def measurements_meta() -> list[dict]:
    return read_json(META / "ripe_atlas_measurements.json")["measurements"]


def predict_series(series_df: pd.DataFrame):
    """LSTM + persistence predictions for EVERY window of one probe/measurement series (all splits).

    Uses the exported numpy inference path (same as the integrated API). Returns a DataFrame.
    """
    from src.prediction.dataset import make_windows
    from src.prediction.features import Scaler, last_log_rtt, target_from_model
    from src.prediction.model import NumpyLSTM

    meta = read_json(MODEL_DIR / "preprocessing.json")
    scaler = Scaler.from_dict(meta["scaler"])
    net = NumpyLSTM(MODEL_DIR / "weights.npz")
    w = make_windows(series_df, split_cutoffs())
    rows = []
    for s, label in (("train", "train"), ("val", "validation"), ("test", "test")):
        X = w[f"X_{s}"]
        if len(X) == 0:
            continue
        y = scaler.y_inverse(net.predict(scaler.x(X)))
        if meta.get("target_mode") == "residual":
            y = y + last_log_rtt(X)
        rows.append(pd.DataFrame({"timestamp": w[f"ts_{s}"], "actual_ms": w[f"y_ms_{s}"],
                                  "lstm_ms": target_from_model(y), "persistence_ms": w[f"last_ms_{s}"], "split": label}))
    if not rows:
        return pd.DataFrame(columns=["timestamp", "actual_ms", "lstm_ms", "persistence_ms", "split", "time_utc"])
    out = pd.concat(rows).sort_values("timestamp")
    out["time_utc"] = pd.to_datetime(out["timestamp"], unit="s", utc=True)
    return out


def mae_rmse(a: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    e = np.asarray(p, float) - np.asarray(a, float)
    return float(np.mean(np.abs(e))), float(np.sqrt(np.mean(e**2)))
