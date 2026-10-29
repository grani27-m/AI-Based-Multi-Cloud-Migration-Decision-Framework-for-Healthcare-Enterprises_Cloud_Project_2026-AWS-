"""
data_ingestion/replay.py  —  Owner: Charles (data)  /  used by Rani's demo endpoint
=====================================================================================
Build API events from REAL recorded data (source = "replay"):

  * network_window : 20 consecutive RIPE Atlas ping rounds from the HELD-OUT TEST period
                     (never used for training), one probe/measurement series;
  * vitals         : one second of a real BIDMC ICU recording (HR, RESP, SpO2);
  * cloud_cost_index: SYNTHETIC time-of-day tariff proxy (labelled in provenance) because
                     no real per-request price feed is part of the project data.

The pairing of a network path with a patient recording is artificial (they were not
recorded together) and is stated in every event's provenance.

Uses dataset/processed/ripe_atlas_clean.csv.gz when present (full rebuild), otherwise
the committed sample dataset/samples/ripe_atlas_test_sample.csv.gz.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.prediction.features import RAW_COLUMNS, WINDOW

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "dataset" / "processed" / "ripe_atlas_clean.csv.gz"
SAMPLE = ROOT / "dataset" / "samples" / "ripe_atlas_test_sample.csv.gz"
BIDMC = ROOT / "dataset" / "samples" / "bidmc_vitals_1hz.csv.gz"
SPLITS = ROOT / "dataset" / "metadata" / "ripe_atlas_splits.json"


def cost_index_for(ts: datetime) -> float:
    """Synthetic tariff proxy: higher during Indian business hours (IST = UTC+5:30)."""
    h = (ts.hour + ts.minute / 60 + 5.5) % 24
    return round(0.25 + 0.45 * max(0.0, math.sin(math.pi * (h - 7) / 14)) if 7 <= h <= 21 else 0.25, 3)


@lru_cache(maxsize=1)
def _network() -> pd.DataFrame:
    path = FULL if FULL.exists() else SAMPLE
    df = pd.read_csv(path)
    test_start = json.loads(SPLITS.read_text())["test"][0]
    t0 = int(datetime.fromisoformat(test_start).timestamp())
    return df[df["timestamp"] >= t0].reset_index(drop=True)


@lru_cache(maxsize=1)
def _vitals() -> pd.DataFrame:
    return pd.read_csv(BIDMC)


def _windows_index(df: pd.DataFrame) -> list[tuple[int, int]]:
    """(start_row, series_len) for every segment long enough for a full window."""
    out = []
    for _, g in df.groupby("segment", sort=False):
        if len(g) >= WINDOW:
            out.append((int(g.index[0]), len(g)))
    return out


def build_replay_events(n: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    df, vit = _network(), _vitals()
    segs = _windows_index(df)
    events = []
    tries = 0
    while len(events) < n and tries < n * 20:
        tries += 1
        start, length = rng.choice(segs)
        i = start + rng.randrange(0, length - WINDOW + 1)
        rows = df.iloc[i : i + WINDOW]
        if rows["rtt_avg_ms"].isna().all():
            continue
        window = []
        for r in rows.itertuples(index=False):
            ob = {"timestamp": datetime.fromtimestamp(int(r.timestamp), timezone.utc).isoformat()}
            for c in RAW_COLUMNS:
                v = getattr(r, c)
                ob[c] = None if (isinstance(v, float) and math.isnan(v)) else float(v)
            if ob["loss_pct"] < 100 and ob["jitter_ms"] is None:
                ob["jitter_ms"] = 0.0
            window.append(ob)
        v = vit.iloc[rng.randrange(len(vit))]
        last_ts = datetime.fromisoformat(window[-1]["timestamp"])
        msm, prb = int(rows.iloc[0]["msm_id"]), int(rows.iloc[0]["prb_id"])
        events.append(
            {
                "event_id": f"replay-{msm}-{prb}-{int(rows.iloc[-1]['timestamp'])}-b{int(v.record_id):02d}-{int(v.t_s)}",
                "device_id": f"ICU-BIDMC-{int(v.record_id):02d}",
                "device_kind": "bedside-monitor",
                "source": "replay",
                "network_window": window,
                "vitals": {"hr": float(v.hr), "resp": float(v.resp), "spo2": float(v.spo2)},
                "cloud_cost_index": cost_index_for(last_ts),
                "provenance": {
                    "network": f"RIPE Atlas msm {msm}, probe {prb}, test period (held out)",
                    "network_group": str(rows.iloc[0]["group"]),
                    "vitals": f"PhysioNet BIDMC record {int(v.record_id):02d}, t={int(v.t_s)} s",
                    "pairing": "artificial (network path and patient recorded independently)",
                    "cost_index": "synthetic time-of-day tariff proxy",
                },
            }
        )
    return events
