"""
src/decision/criticality.py  —  Owner: Tanmay Kapoor
======================================================
Derive the 0-10 patient-criticality criterion from vital signs.

Method: a PARTIAL NEWS2 score (Royal College of Physicians, National Early Warning
Score 2, 2017) using only the three parameters available in the BIDMC numerics:
respiration rate, SpO2 (scale 1) and heart/pulse rate. Each contributes 0-3 points.

    criticality = min(10, aggregate * 10 / 7)

so the full NEWS2 "emergency response" trigger (aggregate >= 7) maps to criticality 10,
and the decision engine's emergency override (>= 9.0) fires exactly when the partial
aggregate is >= 7. Aggregate 6 -> 8.57 (no override).

LIMITATIONS (stated wherever the score is shown): temperature, systolic BP,
consciousness and supplemental O2 are not available, so this is an ILLUSTRATIVE
research score, not a clinically validated early-warning system.
"""

from __future__ import annotations

from dataclasses import dataclass


def _rr_points(rr: float) -> int:
    if rr <= 8:
        return 3
    if rr <= 11:
        return 1
    if rr <= 20:
        return 0
    if rr <= 24:
        return 2
    return 3


def _spo2_points(s: float) -> int:
    if s <= 91:
        return 3
    if s <= 93:
        return 2
    if s <= 95:
        return 1
    return 0


def _hr_points(hr: float) -> int:
    if hr <= 40:
        return 3
    if hr <= 50:
        return 1
    if hr <= 90:
        return 0
    if hr <= 110:
        return 1
    if hr <= 130:
        return 2
    return 3


@dataclass
class CriticalityResult:
    score: float
    aggregate: int
    points: dict
    method: str = "partial_news2_v1 (RR, SpO2, HR) - illustrative, not clinically validated"

    def to_dict(self) -> dict:
        return {"score": self.score, "aggregate": self.aggregate, "points": self.points, "method": self.method}


def criticality_from_vitals(hr: float, resp: float, spo2: float) -> CriticalityResult:
    for name, v, lo, hi in (("hr", hr, 10, 300), ("resp", resp, 0, 80), ("spo2", spo2, 30, 100)):
        if v is None or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ValueError(f"{name}={v!r} outside plausible range {lo}-{hi}")
    pts = {"resp": _rr_points(resp), "spo2": _spo2_points(spo2), "hr": _hr_points(hr)}
    agg = sum(pts.values())
    return CriticalityResult(score=round(min(10.0, agg * 10.0 / 7.0), 2), aggregate=agg, points=pts)
