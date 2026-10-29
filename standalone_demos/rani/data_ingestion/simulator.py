"""
data_ingestion/simulator.py  —  Owner: Charles
================================================
Deterministic SIMULATED IoMT stream (source = "simulated") for controlled tests and
demonstrations of situations that are rare in the real data (e.g. RTT >= 300 ms occurs
in only 47 of 753,410 real RIPE Atlas rounds).

Scenarios
    normal     stable 10-40 ms path, routine vitals
    degraded   RTT ramps from ~60 ms towards 400-600 ms with rising loss/jitter
    emergency  normal path, critical vitals (partial NEWS2 >= 7 -> criticality 10)
    failure    normal path, routine vitals, cloud execution failure injected
    mixed      70 % normal, 12 % degraded, 10 % emergency, 8 % failure

Every record is synthetic and labelled as such; the same seed reproduces the run.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from src.prediction.features import WINDOW

DEVICES = [
    ("SIM-ECG-101", "ecg"),
    ("SIM-SPO2-201", "pulse-oximeter"),
    ("SIM-WEAR-301", "wearable"),
    ("SIM-BP-401", "bp-monitor"),
    ("SIM-RESP-501", "respiratory"),
]
BASE_TIME = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _window(rng: random.Random, scenario: str, t_end: datetime) -> list[dict]:
    base = rng.uniform(10, 40)
    out = []
    for k in range(WINDOW):
        ts = t_end - timedelta(seconds=240 * (WINDOW - 1 - k))
        if scenario == "degraded":
            frac = k / (WINDOW - 1)
            avg = 60 + frac**2 * rng.uniform(350, 550) + rng.gauss(0, 8)
            loss = min(100.0, frac * rng.uniform(5, 25))
        else:
            avg = base + rng.gauss(0, 2.5)
            loss = 0.0 if rng.random() > 0.05 else 33.3
        avg = max(1.0, avg)
        jit = abs(rng.gauss(avg * 0.05, avg * 0.02))
        out.append(
            {
                "timestamp": ts.isoformat(),
                "rtt_avg_ms": round(avg, 3),
                "rtt_min_ms": round(max(0.5, avg - jit), 3),
                "rtt_max_ms": round(avg + jit, 3),
                "jitter_ms": round(jit, 3),
                "loss_pct": round(loss, 1),
            }
        )
    return out


def _vitals(rng: random.Random, critical: bool) -> dict:
    if critical:
        return {"hr": rng.uniform(132, 160), "resp": rng.uniform(26, 34), "spo2": rng.uniform(84, 90)}
    return {"hr": rng.uniform(62, 88), "resp": rng.uniform(13, 19), "spo2": rng.uniform(96, 99)}


def build_simulated_events(n: int, scenario: str = "mixed", seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    events = []
    for i in range(n):
        sc = scenario
        if scenario == "mixed":
            r = rng.random()
            sc = "normal" if r < 0.70 else "degraded" if r < 0.82 else "emergency" if r < 0.92 else "failure"
        dev, kind = DEVICES[i % len(DEVICES)]
        t_end = BASE_TIME + timedelta(minutes=4 * i)
        ev = {
            "event_id": f"sim-{seed}-{scenario}-{i:05d}",
            "device_id": dev,
            "device_kind": kind,
            "source": "simulated",
            "network_window": _window(rng, sc, t_end),
            "vitals": {k: round(v, 1) for k, v in _vitals(rng, sc == "emergency").items()},
            "cloud_cost_index": round(rng.uniform(0.1, 0.9), 3),
            "provenance": {"generator": "data_ingestion/simulator.py", "scenario": sc, "seed": seed, "synthetic": True},
        }
        if sc == "failure":
            ev["simulate_failure"] = "cloud"
        events.append(ev)
    return events
