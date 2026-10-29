"""
src/prediction/ripe_parser.py  —  Owner: Charles
=================================================
Turn raw RIPE Atlas ping results into one validated row per measurement round.

Field provenance (documented in reports/DATASET_REPORT.md)
----------------------------------------------------------
OBSERVED by RIPE Atlas      : timestamp, prb_id, msm_id, sent, rcvd, min, max, avg,
                              per-packet RTTs in result[].rtt
DERIVED here (documented)   : loss_pct  = 100 * (sent - rcvd) / sent
                              jitter_ms = mean |rtt_k - rtt_(k-1)| over consecutive
                                          successful replies of the same round
                                          (an IPDV-style estimate; NaN if < 2 replies)
NOT AVAILABLE (never invented): bandwidth, wireless signal strength. The previous
                              downloader fabricated both from RTT with a formula; that
                              was removed because the model would only re-learn the formula.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Iterable, Iterator

MAX_VALID_RTT_MS = 5000.0  # anything above is a malformed record, not a slow network

PARSED_COLUMNS = [
    "msm_id",
    "prb_id",
    "timestamp",
    "sent",
    "rcvd",
    "rtt_avg_ms",
    "rtt_min_ms",
    "rtt_max_ms",
    "loss_pct",
    "jitter_ms",
    "invalid_reason",
]


def _jitter(rtts: list[float]) -> float:
    if len(rtts) < 2:
        return math.nan
    return sum(abs(b - a) for a, b in zip(rtts, rtts[1:])) / (len(rtts) - 1)


def parse_result(r: dict) -> dict:
    """Parse one ping result. Always returns a row; problems are flagged in invalid_reason."""
    row = {
        "msm_id": r.get("msm_id"),
        "prb_id": r.get("prb_id"),
        "timestamp": r.get("timestamp"),
        "sent": r.get("sent"),
        "rcvd": r.get("rcvd"),
        "rtt_avg_ms": math.nan,
        "rtt_min_ms": math.nan,
        "rtt_max_ms": math.nan,
        "loss_pct": math.nan,
        "jitter_ms": math.nan,
        "invalid_reason": "",
    }
    if r.get("type") not in (None, "ping"):
        row["invalid_reason"] = "not_ping"
        return row
    if "error" in r or not isinstance(row["timestamp"], int):
        row["invalid_reason"] = "probe_error"
        return row
    sent, rcvd = row["sent"], row["rcvd"]
    if not isinstance(sent, int) or not isinstance(rcvd, int) or sent <= 0 or rcvd < 0 or rcvd > sent:
        row["invalid_reason"] = "bad_counts"
        return row
    row["loss_pct"] = 100.0 * (sent - rcvd) / sent
    rtts = [
        float(x["rtt"]) for x in r.get("result", []) if isinstance(x, dict) and isinstance(x.get("rtt"), (int, float))
    ]
    if rcvd == 0:
        return row  # valid round with 100 % loss; RTTs legitimately unknown
    avg, mn, mx = r.get("avg"), r.get("min"), r.get("max")
    if not all(isinstance(v, (int, float)) and 0 < v < MAX_VALID_RTT_MS for v in (avg, mn, mx)) or not (
        mn <= avg <= mx
    ):
        row["invalid_reason"] = "bad_rtt"
        return row
    row.update(rtt_avg_ms=float(avg), rtt_min_ms=float(mn), rtt_max_ms=float(mx), jitter_ms=_jitter(rtts))
    return row


def iter_raw_file(path: Path) -> Iterator[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        yield from json.load(f)


def parse_files(paths: Iterable[Path]) -> Iterator[dict]:
    for p in paths:
        for r in iter_raw_file(p):
            yield parse_result(r)
