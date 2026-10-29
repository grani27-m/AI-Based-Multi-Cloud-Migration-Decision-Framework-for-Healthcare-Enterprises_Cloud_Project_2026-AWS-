"""Charles package test fixtures (package-only file). SYNTHETIC windows, used only by tests."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def window(base=20.0, step=0.0, n=20, start=None, loss=0.0):
    start = start or datetime(2026, 10, 20, tzinfo=timezone.utc)
    return [
        {
            "timestamp": (start + timedelta(seconds=240 * k)).isoformat(),
            "rtt_avg_ms": base + step * k,
            "rtt_min_ms": (base + step * k) * 0.95,
            "rtt_max_ms": (base + step * k) * 1.05,
            "jitter_ms": (base + step * k) * 0.02,
            "loss_pct": loss,
        }
        for k in range(n)
    ]
