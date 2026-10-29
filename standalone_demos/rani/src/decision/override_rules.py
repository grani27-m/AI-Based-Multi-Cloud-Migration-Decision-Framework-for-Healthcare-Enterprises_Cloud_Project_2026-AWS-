"""
src/decision/override_rules.py  —  Owner: Tanmay Kapoor
=========================================================
Stage A hard safety vetoes, evaluated BEFORE any AHP arithmetic.

  1. Emergency override : patient criticality >= 9.0          -> EDGE
  2. Network veto        : predicted latency  >= 300 ms        -> EDGE
  3. Missing prediction  : no latency forecast available       -> EDGE (safe default)

Thresholds are configurable through the environment (EMERGENCY_CRITICALITY_THRESHOLD,
LATENCY_VETO_MS) but default to the values in the project report. They are design
parameters that would need clinical review before real use.
"""

from __future__ import annotations

import os

EMERGENCY_CRITICALITY_THRESHOLD: float = float(os.environ.get("EMERGENCY_CRITICALITY_THRESHOLD", 9.0))
LATENCY_VETO_MS: float = float(os.environ.get("LATENCY_VETO_MS", 300.0))


def check_emergency_override(
    patient_criticality_score: float, threshold: float = EMERGENCY_CRITICALITY_THRESHOLD
) -> bool:
    return patient_criticality_score >= threshold


def check_network_veto(predicted_latency_ms: float | None, threshold: float = LATENCY_VETO_MS) -> bool:
    return predicted_latency_ms is not None and predicted_latency_ms >= threshold
