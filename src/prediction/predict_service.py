"""
src/prediction/predict_service.py  —  Owner: Charles
=====================================================
Online inference contract consumed by Rani's pipeline (backend/services/pipeline.py).

    predictor = LatencyPredictor.load()            # once at startup
    result = predictor.predict(window)             # window = 20 NetworkObservation dicts

Input  (each of exactly 20 items, oldest -> newest):
    {"timestamp": ISO-8601 or unix seconds, "rtt_avg_ms": float|None, "rtt_min_ms": float|None,
     "rtt_max_ms": float|None, "jitter_ms": float|None, "loss_pct": float 0-100}
    rtt_* may be None only for a round with loss_pct == 100.

Output (PredictionResult.to_dict()):
    predicted_rtt_ms, risk (LOW <75 | MEDIUM <150 | HIGH), method, model_version,
    horizon_s, inference_ms, last_observed_rtt_ms

`method` is ALWAYS explicit:
    "lstm"                  the trained network produced the value
    "persistence_fallback"  model artifacts missing/unloadable -> last observed RTT is used.
                            Never presented as a model prediction (the old code silently
                            returned last_latency * 1.1 and reported it as the LSTM's output).
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from src.prediction.features import RAW_COLUMNS, WINDOW, Scaler, target_from_model, transform_raw
from src.prediction.model import NumpyLSTM

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = ROOT / "models" / "latency_lstm"
RISK_THRESHOLDS_MS = (75.0, 150.0)
log = logging.getLogger("predict_service")


class PredictionInputError(ValueError):
    """Raised for malformed windows. The API maps it to HTTP 422."""


@dataclass
class PredictionResult:
    predicted_rtt_ms: float
    risk: str
    method: str
    model_version: str
    horizon_s: int
    inference_ms: float
    last_observed_rtt_ms: float

    def to_dict(self) -> dict:
        return asdict(self)


def classify_risk(ms: float) -> str:
    return "LOW" if ms < RISK_THRESHOLDS_MS[0] else "MEDIUM" if ms < RISK_THRESHOLDS_MS[1] else "HIGH"


def _to_unix(ts: Any) -> float:
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        return float(ts)
    if isinstance(ts, datetime):
        return ts.timestamp()
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    raise PredictionInputError(f"bad timestamp {ts!r}")


def validate_window(window: Sequence[dict]) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(window, (list, tuple)) or len(window) != WINDOW:
        raise PredictionInputError(f"window must contain exactly {WINDOW} observations, got "
                                   f"{len(window) if hasattr(window, '__len__') else type(window).__name__}")
    ts = np.array([_to_unix(o.get("timestamp")) for o in window])
    if np.any(np.diff(ts) <= 0):
        raise PredictionInputError("timestamps must be strictly increasing (oldest -> newest)")
    raw = np.full((WINDOW, len(RAW_COLUMNS)), np.nan)
    for i, o in enumerate(window):
        loss = o.get("loss_pct")
        if not isinstance(loss, (int, float)) or not 0 <= loss <= 100:
            raise PredictionInputError(f"observation {i}: loss_pct must be 0-100")
        for j, c in enumerate(RAW_COLUMNS):
            v = o.get(c)
            if v is None:
                if c == "loss_pct" or (c != "jitter_ms" and loss < 100):
                    raise PredictionInputError(f"observation {i}: {c} is required unless loss_pct == 100")
                continue
            if not isinstance(v, (int, float)) or math.isnan(v) or v < 0 or v > 5000:
                raise PredictionInputError(f"observation {i}: {c}={v!r} out of range 0-5000")
            raw[i, j] = float(v)
    if np.isnan(raw[:, 0]).all():
        raise PredictionInputError("window has no successful round (100 % loss everywhere)")
    return raw, ts


class LatencyPredictor:
    def __init__(self, net: NumpyLSTM | None, scaler: Scaler | None, meta: dict, load_error: str | None = None):
        self.net, self.scaler, self.meta, self.load_error = net, scaler, meta, load_error

    @classmethod
    def load(cls, model_dir: Path | str = DEFAULT_MODEL_DIR) -> "LatencyPredictor":
        model_dir = Path(model_dir)
        try:
            meta = json.loads((model_dir / "preprocessing.json").read_text())
            return cls(NumpyLSTM(model_dir / "weights.npz"), Scaler.from_dict(meta["scaler"]), meta)
        except Exception as exc:  # explicit, visible degraded mode
            log.warning("LSTM artifacts unavailable in %s (%s); using persistence_fallback", model_dir, exc)
            return cls(None, None, {"model_version": "none"}, load_error=str(exc))

    @property
    def model_loaded(self) -> bool:
        return self.net is not None

    @property
    def model_version(self) -> str:
        return self.meta.get("model_version", "none")

    def predict(self, window: Sequence[dict]) -> PredictionResult:
        raw, ts = validate_window(window)
        last = float(raw[~np.isnan(raw[:, 0]), 0][-1])
        t0 = time.perf_counter()
        if self.net is not None:
            feats = transform_raw(raw, ts)
            y = self.scaler.y_inverse(self.net.predict(self.scaler.x(feats)[None, ...]))
            if self.meta.get("target_mode") == "residual":
                y = y + feats[-1, 0]  # add back log1p(last RTT)
            pred = float(target_from_model(y)[0])
            method, version = "lstm", self.model_version
        else:
            pred, method, version = last, "persistence_fallback", "none"
        pred = max(0.0, pred)
        return PredictionResult(predicted_rtt_ms=round(pred, 3), risk=classify_risk(pred), method=method,
                                model_version=version, horizon_s=240,
                                inference_ms=round((time.perf_counter() - t0) * 1000, 3),
                                last_observed_rtt_ms=round(last, 3))

    def info(self) -> dict:
        return {"loaded": self.model_loaded, "model_version": self.model_version, "load_error": self.load_error,
                "window": WINDOW, "features": self.meta.get("features"), "architecture": self.meta.get("architecture"),
                "training": self.meta.get("training"), "trained_at": self.meta.get("trained_at"),
                "risk_thresholds_ms": RISK_THRESHOLDS_MS}
