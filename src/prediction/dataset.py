"""
src/prediction/dataset.py  —  Owner: Charles
=============================================
Raw RIPE Atlas chunks  ->  cleaned table  ->  chronological train/val/test windows.

    python -m src.prediction.dataset build

Outputs (all regenerated from dataset/raw, never edited by hand)
    dataset/processed/ripe_atlas_clean.csv.gz       one row per valid ping round
    dataset/processed/windows_w20.npz               X/y arrays per split (+ baseline helpers)
    dataset/metadata/ripe_atlas_quality.json        counts before/after every cleaning step
    dataset/metadata/ripe_atlas_splits.json         split cut-offs and sizes

Leakage controls
    * splits are by TIME (same cut-offs for every probe), never shuffled;
    * a window is assigned to a split only if all 21 timestamps (20 inputs + target)
      fall inside that split's interval;
    * the scaler is fitted on training windows only (see train.py).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.prediction.features import RAW_COLUMNS, WINDOW, transform_raw, target_to_model
from src.prediction.ripe_parser import parse_files

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "dataset" / "raw" / "ripe_atlas"
PROC = ROOT / "dataset" / "processed"
META = ROOT / "dataset" / "metadata"
CONFIG = ROOT / "dataset" / "config" / "ripe_atlas_selection.json"

MAX_GAP_S = 360          # > 1.5 x 240 s interval => the series is broken into a new segment
SPLIT_FRACTIONS = (0.70, 0.15, 0.15)
log = logging.getLogger("dataset")


def _probe_groups() -> dict[int, str]:
    cfg = json.loads(CONFIG.read_text())
    return {int(p): g for g, ids in cfg["probes"].items() for p in ids}


def load_clean(raw_dir: Path = RAW_DIR) -> tuple[pd.DataFrame, dict]:
    files = sorted(raw_dir.rglob("*.json.gz"))
    if not files:
        raise FileNotFoundError(f"no raw chunks under {raw_dir}; run python -m data_ingestion.ripe_atlas download")
    df = pd.DataFrame(parse_files(files))
    q: dict = {"raw_files": len(files), "rows_raw": int(len(df))}
    q["invalid_by_reason"] = {k: int(v) for k, v in df["invalid_reason"].value_counts().items() if k}
    df = df[df["invalid_reason"] == ""].drop(columns="invalid_reason")
    q["rows_after_validity"] = int(len(df))
    before = len(df)
    df = df.drop_duplicates(["msm_id", "prb_id", "timestamp"])
    q["duplicates_removed"] = int(before - len(df))
    df = df.astype({"msm_id": int, "prb_id": int, "timestamp": int})
    df["group"] = df["prb_id"].map(_probe_groups()).fillna("unknown")
    df["series_id"] = df["msm_id"].astype(str) + "-" + df["prb_id"].astype(str)
    df = df.sort_values(["series_id", "timestamp"]).reset_index(drop=True)
    gap = df.groupby("series_id")["timestamp"].diff()
    df["segment"] = (gap.isna() | (gap > MAX_GAP_S)).cumsum()
    q["rows_clean"] = int(len(df))
    q["rows_total_loss"] = int((df["rcvd"] == 0).sum())
    q["rows_jitter_undefined"] = int(df["jitter_ms"].isna().sum() - (df["rcvd"] == 0).sum())
    q["series"] = int(df["series_id"].nunique())
    q["segments"] = int(df["segment"].nunique())
    q["time_range_utc"] = [datetime.fromtimestamp(int(df.timestamp.min()), timezone.utc).isoformat(),
                           datetime.fromtimestamp(int(df.timestamp.max()), timezone.utc).isoformat()]
    rtt = df["rtt_avg_ms"].dropna()
    q["rtt_avg_ms"] = {k: round(float(v), 3) for k, v in rtt.describe(percentiles=[.5, .95, .99]).items()}
    q["rows_rtt_ge_150ms"] = int((rtt >= 150).sum())
    q["rows_rtt_ge_300ms"] = int((rtt >= 300).sum())
    q["rows_per_group"] = {k: int(v) for k, v in df["group"].value_counts().items()}
    q["rows_per_probe"] = {str(k): int(v) for k, v in df.groupby("prb_id").size().items()}
    return df, q


def make_windows(df: pd.DataFrame, cutoffs: tuple[int, int]) -> dict:
    """Build windows per segment and assign each to train/val/test by its whole time span."""
    t1, t2 = cutoffs
    parts = {s: {"X": [], "y": [], "last": [], "ts": [], "sid": [], "grp": []} for s in ("train", "val", "test")}
    sid_codes = {s: i for i, s in enumerate(sorted(df.series_id.unique()))}
    for seg, g in df.groupby("segment", sort=False):
        if len(g) <= WINDOW:
            continue
        ts = g["timestamp"].to_numpy()
        feats = transform_raw(g[RAW_COLUMNS].to_numpy(dtype=np.float64), ts)
        target_raw = g["rtt_avg_ms"].to_numpy(dtype=np.float64)
        last_raw = pd.Series(target_raw).ffill().bfill().to_numpy()  # persistence baseline input
        n = len(g) - WINDOW
        idx = np.arange(n)
        valid = ~np.isnan(target_raw[WINDOW:])  # target round must have an RTT (not 100 % loss)
        start_ts, end_ts = ts[idx], ts[idx + WINDOW]
        split = np.where(end_ts < t1, "train", np.where((start_ts >= t1) & (end_ts < t2), "val",
                                                         np.where(start_ts >= t2, "test", "boundary")))
        from numpy.lib.stride_tricks import sliding_window_view
        win = sliding_window_view(feats, (WINDOW, feats.shape[1]))[:, 0][:n]
        for s in ("train", "val", "test"):
            m = valid & (split == s)
            if not m.any():
                continue
            p = parts[s]
            p["X"].append(win[m].astype(np.float32))
            p["y"].append(target_raw[WINDOW:][m])
            p["last"].append(last_raw[WINDOW - 1:-1][m])
            p["ts"].append(end_ts[m])
            p["sid"].append(np.full(m.sum(), sid_codes[g["series_id"].iat[0]]))
            p["grp"].append(np.full(m.sum(), g["group"].iat[0]))
    out = {}
    for s, p in parts.items():
        out[f"X_{s}"] = np.concatenate(p["X"]) if p["X"] else np.zeros((0, WINDOW, 7), np.float32)
        out[f"y_ms_{s}"] = np.concatenate(p["y"]) if p["y"] else np.zeros(0)
        out[f"y_{s}"] = target_to_model(out[f"y_ms_{s}"]).astype(np.float32)
        out[f"last_ms_{s}"] = np.concatenate(p["last"]) if p["last"] else np.zeros(0)
        out[f"ts_{s}"] = np.concatenate(p["ts"]) if p["ts"] else np.zeros(0, int)
        out[f"series_{s}"] = np.concatenate(p["sid"]) if p["sid"] else np.zeros(0, int)
        out[f"group_{s}"] = np.concatenate(p["grp"]) if p["grp"] else np.zeros(0, "<U16")
    out["series_names"] = np.array(sorted(sid_codes, key=sid_codes.get))
    return out


def build() -> dict:
    df, q = load_clean()
    PROC.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROC / "ripe_atlas_clean.csv.gz", index=False, compression="gzip")
    tmin, tmax = int(df.timestamp.min()), int(df.timestamp.max())
    span = tmax - tmin
    cut = (tmin + int(span * SPLIT_FRACTIONS[0]), tmin + int(span * (SPLIT_FRACTIONS[0] + SPLIT_FRACTIONS[1])))
    w = make_windows(df, cut)
    np.savez_compressed(PROC / "windows_w20.npz", **w)
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()  # noqa: E731
    splits = {"method": "global chronological cut-offs; whole window must lie inside one split",
              "fractions": SPLIT_FRACTIONS, "train": [iso(tmin), iso(cut[0])], "val": [iso(cut[0]), iso(cut[1])],
              "test": [iso(cut[1]), iso(tmax)],
              "windows": {s: int(len(w[f"y_{s}"])) for s in ("train", "val", "test")}}
    (META / "ripe_atlas_splits.json").write_text(json.dumps(splits, indent=2))
    q["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    q["windows"] = splits["windows"]
    (META / "ripe_atlas_quality.json").write_text(json.dumps(q, indent=2))
    log.info("quality: %s", json.dumps(q)[:600])
    log.info("splits: %s", splits)
    return q


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 2 or sys.argv[1] != "build":
        print("usage: python -m src.prediction.dataset build")
        raise SystemExit(2)
    build()
