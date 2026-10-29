"""
src/prediction/features.py  —  Owner: Charles
==============================================
Single source of truth for the model's input features. Used by training
(src/prediction/dataset.py) AND by online inference (predict_service.py), so the
two can never drift apart.

One time step = one RIPE Atlas ping round (or one equivalent device observation):
    rtt_avg_ms, rtt_min_ms, rtt_max_ms   observed
    jitter_ms                            derived (mean |delta rtt| within the round)
    loss_pct                             derived (100*(sent-rcvd)/sent)
    hour_sin, hour_cos                   derived from the UTC timestamp (daily cycle)
Target: rtt_avg_ms of the NEXT round (one measurement interval ahead, 240 s for
RIPE built-in measurements).
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

WINDOW = 20
RAW_COLUMNS = ["rtt_avg_ms", "rtt_min_ms", "rtt_max_ms", "jitter_ms", "loss_pct"]
FEATURES = RAW_COLUMNS + ["hour_sin", "hour_cos"]
LOG_COLUMNS = ["rtt_avg_ms", "rtt_min_ms", "rtt_max_ms", "jitter_ms"]  # log1p-compressed (heavy tails)
TARGET = "rtt_avg_ms"


def fill_missing(arr: np.ndarray) -> np.ndarray:
    """Forward-fill NaNs along time (axis 0) per column, then back-fill, then 0 for jitter/loss.

    A round with 100 % packet loss has no RTT; the last known RTT is carried forward
    and the loss_pct column (=100) tells the model what happened.
    """
    out = arr.astype(np.float64, copy=True)
    for j in range(out.shape[1]):
        col = out[:, j]
        mask = np.isnan(col)
        if not mask.any():
            continue
        idx = np.where(~mask, np.arange(len(col)), 0)
        np.maximum.accumulate(idx, out=idx)
        col[:] = col[idx]
        if np.isnan(col).any():  # leading NaNs -> back-fill with first valid value
            valid = np.flatnonzero(~np.isnan(col))
            col[np.isnan(col)] = col[valid[0]] if len(valid) else 0.0
    return out


def transform_raw(raw: np.ndarray, timestamps: Sequence[float]) -> np.ndarray:
    """raw: (T, 5) in RAW_COLUMNS order, NaN allowed. Returns (T, 7) unscaled model features."""
    x = fill_missing(raw)
    for c in LOG_COLUMNS:
        j = RAW_COLUMNS.index(c)
        x[:, j] = np.log1p(np.clip(x[:, j], 0, None))
    x[:, RAW_COLUMNS.index("loss_pct")] /= 100.0
    hours = (np.asarray(timestamps, dtype=np.float64) % 86400) / 3600.0
    return np.column_stack([x, np.sin(2 * math.pi * hours / 24), np.cos(2 * math.pi * hours / 24)])


RTT_IDX = 0  # position of rtt_avg_ms in FEATURES


def target_to_model(rtt_ms: np.ndarray) -> np.ndarray:
    return np.log1p(rtt_ms)


def target_from_model(y: np.ndarray) -> np.ndarray:
    return np.expm1(y)


def last_log_rtt(x_unscaled: np.ndarray) -> np.ndarray:
    """log1p of the last (carried-forward) RTT in each window; x_unscaled: (batch, WINDOW, F)."""
    return np.asarray(x_unscaled[:, -1, RTT_IDX], dtype=np.float64)


# target_mode "residual": the network predicts log1p(next RTT) - log1p(last RTT).
# A zero output therefore equals the persistence forecast; the LSTM learns corrections.


class Scaler:
    """Standard scaler (mean/std) whose parameters are stored as plain JSON."""

    def __init__(self, mean, std, y_mean: float, y_std: float):
        self.mean = np.asarray(mean, dtype=np.float64)
        self.std = np.where(np.asarray(std, dtype=np.float64) < 1e-8, 1.0, np.asarray(std, dtype=np.float64))
        self.y_mean, self.y_std = float(y_mean), float(y_std)

    @classmethod
    def fit(cls, x2d: np.ndarray, y: np.ndarray) -> "Scaler":
        return cls(x2d.mean(0), x2d.std(0), float(y.mean()), float(y.std()))

    def x(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean) / self.std).astype(np.float32)

    def y(self, y: np.ndarray) -> np.ndarray:
        return ((y - self.y_mean) / self.y_std).astype(np.float32)

    def y_inverse(self, y_scaled: np.ndarray) -> np.ndarray:
        return np.asarray(y_scaled, dtype=np.float64) * self.y_std + self.y_mean

    def to_dict(self) -> dict:
        return {"mean": self.mean.tolist(), "std": self.std.tolist(), "y_mean": self.y_mean, "y_std": self.y_std}

    @classmethod
    def from_dict(cls, d: dict) -> "Scaler":
        return cls(d["mean"], d["std"], d["y_mean"], d["y_std"])
