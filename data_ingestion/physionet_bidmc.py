"""
data_ingestion/physionet_bidmc.py  —  Owner: Charles (24BIT0522)
====================================================================
Download REAL de-identified ICU vital signs from the PhysioNet BIDMC dataset
(v1.0.0, 53 adult ICU recordings, 8 minutes each, numerics at 1 Hz:
HR, PULSE, RESP, SpO2).

Source  : https://physionet.org/content/bidmc/1.0.0/
Licence : Open Data Commons Attribution License v1.0 (open access, no credentialing)
Cite    : Pimentel M.A.F. et al. "Towards a Robust Estimation of Respiratory Rate from
          Pulse Oximeters", IEEE TBME 64(8):1914-1923, 2016; and Goldberger A.L. et al.,
          PhysioBank/PhysioToolkit/PhysioNet, Circulation 101(23):e215-e220, 2000.

What it is used for in this project
-----------------------------------
The vital signs are NOT network data and are never fed to the latency model.
They drive the *patient-criticality* criterion of the decision engine during
replay demonstrations (see src/decision/criticality.py). Only numerics are
downloaded; the age/gender header files are not needed and are not stored.

Usage:  python -m data_ingestion.physionet_bidmc download
        python -m data_ingestion.physionet_bidmc build
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://physionet.org/files/bidmc/1.0.0"
RAW = ROOT / "dataset" / "raw" / "physionet_bidmc"
OUT = ROOT / "dataset" / "processed" / "bidmc_vitals_1hz.csv"
META = ROOT / "dataset" / "metadata" / "physionet_bidmc_manifest.json"
log = logging.getLogger("bidmc")


def _get(url: str) -> bytes:
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == 3:
                raise


def download() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    sums = {}
    for line in _get(f"{BASE}/SHA256SUMS.txt").decode().splitlines():
        h, name = line.split(maxsplit=1)
        sums[name.strip()] = h
    names = sorted(n for n in sums if n.startswith("bidmc_csv/") and n.endswith("_Numerics.csv"))
    entries = []
    for n in names:
        dest = RAW / Path(n).name
        if not dest.exists():
            dest.write_bytes(_get(f"{BASE}/{n}"))
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        ok = digest == sums[n]
        if not ok:
            log.error("checksum mismatch for %s", n)
        entries.append({"file": str(dest.relative_to(ROOT)), "url": f"{BASE}/{n}",
                        "sha256": digest, "checksum_matches_physionet": ok})
    (RAW / "LICENSE").write_bytes(_get(f"{BASE}/LICENSE"))
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps({
        "dataset": "BIDMC PPG and Respiration Dataset v1.0.0",
        "source": "https://physionet.org/content/bidmc/1.0.0/",
        "licence": "Open Data Commons Attribution License v1.0",
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": entries,
    }, indent=2), encoding="utf-8")
    log.info("downloaded/verified %d numerics files (%d checksum failures)",
             len(entries), sum(not e["checksum_matches_physionet"] for e in entries))
    return 0 if all(e["checksum_matches_physionet"] for e in entries) else 1


def build() -> pd.DataFrame:
    """Clean and concatenate numerics into one tidy CSV (record_id, t_s, hr, pulse, resp, spo2)."""
    frames = []
    for f in sorted(RAW.glob("bidmc_*_Numerics.csv")):
        df = pd.read_csv(f, skipinitialspace=True)
        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={"Time [s]": "t_s", "HR": "hr", "PULSE": "pulse", "RESP": "resp", "SpO2": "spo2"})
        df.insert(0, "record_id", f.name.split("_")[1])
        frames.append(df[["record_id", "t_s", "hr", "pulse", "resp", "spo2"]])
    raw = pd.concat(frames, ignore_index=True)
    n_raw = len(raw)
    # Physiologically impossible values are treated as sensor dropouts (NaN), then forward-filled
    # within a record. Plausibility ranges are deliberately wide (not clinical thresholds).
    bounds = {"hr": (20, 250), "pulse": (20, 250), "resp": (2, 70), "spo2": (50, 100)}
    invalid = {}
    for col, (lo, hi) in bounds.items():
        bad = ~raw[col].between(lo, hi)
        invalid[col] = int(bad.sum())
        raw.loc[bad, col] = float("nan")
    raw[list(bounds)] = raw.groupby("record_id")[list(bounds)].ffill()
    clean = raw.dropna(subset=["hr", "resp", "spo2"]).drop_duplicates(["record_id", "t_s"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(OUT, index=False)
    report = {"rows_raw": n_raw, "rows_clean": len(clean), "records": int(clean.record_id.nunique()),
              "out_of_range_set_to_nan": invalid, "rows_dropped_unrecoverable": n_raw - len(clean)}
    (ROOT / "dataset" / "metadata" / "bidmc_quality.json").write_text(json.dumps(report, indent=2))
    log.info("BIDMC build: %s", report)
    return clean


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["download", "build"])
    a = ap.parse_args(argv)
    if a.cmd == "download":
        return download()
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
