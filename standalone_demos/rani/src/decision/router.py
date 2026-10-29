"""
src/decision/router.py  —  Owner: Tanmay Kapoor
=================================================
The decision contract used by Rani's pipeline and by the AWS Lambda handler.

    from src.decision.router import DecisionInput, decide
    result = decide(DecisionInput(device_id="ECG-101", criticality=4.2,
                                  predicted_latency_ms=38.0, cloud_cost_index=0.35))
    result.to_dict()

Two stages
    Stage A  hard vetoes (override_rules.py) -> EDGE, no scoring
    Stage B  AHP-weighted scores for the two alternatives, higher score wins

Stage B formula (kept from the team's original design and documented as a design choice):
    n_c = criticality/10, n_l = min(latency/500, 1), n_k = cost index (0-1)
    EDGE  = w_c * n_c^2       + w_l * n_l       + w_k * n_k
    CLOUD = w_c * (1-n_c)^2   + w_l * (1-n_l)   + w_k * (1-n_k)
The square on criticality makes mid/high criticality favour EDGE more strongly than a
linear AHP sum would. Ties go to EDGE (the clinically safer side).

Invalid input never produces a silent decision: DecisionInputError is raised (HTTP 422).
A missing latency forecast with a valid criticality returns EDGE with
reason "prediction_unavailable_safe_default".
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

from src.decision.ahp import weight_set
from src.decision.override_rules import (
    EMERGENCY_CRITICALITY_THRESHOLD,
    LATENCY_VETO_MS,
    check_emergency_override,
    check_network_veto,
)

ENGINE_VERSION = "ahp-2stage-1.1"
LATENCY_NORMALISATION_MS = 500.0
WEIGHT_SET = os.environ.get("AHP_WEIGHT_SET", "eigenvector")
REASONS = (
    "override_critical_patient",
    "network_degradation_veto",
    "prediction_unavailable_safe_default",
    "ahp_decision",
)


class DecisionInputError(ValueError):
    pass


@dataclass
class DecisionInput:
    device_id: str
    criticality: float
    predicted_latency_ms: Optional[float]
    cloud_cost_index: float

    def validate(self) -> None:
        if not isinstance(self.device_id, str) or not self.device_id.strip():
            raise DecisionInputError("device_id is required")
        for name, v, lo, hi in (
            ("criticality", self.criticality, 0.0, 10.0),
            ("cloud_cost_index", self.cloud_cost_index, 0.0, 1.0),
        ):
            if not isinstance(v, (int, float)) or isinstance(v, bool) or math.isnan(v) or not lo <= v <= hi:
                raise DecisionInputError(f"{name} must be a number in [{lo}, {hi}], got {v!r}")
        p = self.predicted_latency_ms
        if p is not None and (not isinstance(p, (int, float)) or math.isnan(p) or p < 0):
            raise DecisionInputError(f"predicted_latency_ms must be >= 0 or null, got {p!r}")


@dataclass
class DecisionResult:
    device_id: str
    destination: str  # EDGE | CLOUD
    reason: str  # one of REASONS
    veto: str  # none | emergency | network | missing_prediction
    edge_score: Optional[float]
    cloud_score: Optional[float]
    weights: dict
    weight_set: str
    normalised: dict
    contributions: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    engine_version: str = ENGINE_VERSION
    explanation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def normalise(criticality: float, latency_ms: float, cost: float) -> dict:
    return {
        "criticality": criticality / 10.0,
        "latency": min(latency_ms / LATENCY_NORMALISATION_MS, 1.0),
        "cost": min(max(cost, 0.0), 1.0),
    }


def decide(inp: DecisionInput, weight_set_name: str | None = None) -> DecisionResult:
    inp.validate()
    ws = weight_set(weight_set_name or WEIGHT_SET)
    w = ws["weights"]
    thresholds = {"emergency_criticality": EMERGENCY_CRITICALITY_THRESHOLD, "latency_veto_ms": LATENCY_VETO_MS}
    base = dict(device_id=inp.device_id, weights=w, weight_set=ws["name"], thresholds=thresholds)

    if check_emergency_override(inp.criticality):
        return DecisionResult(
            destination="EDGE",
            reason="override_critical_patient",
            veto="emergency",
            edge_score=None,
            cloud_score=None,
            normalised={},
            explanation=f"Criticality {inp.criticality:.2f} >= {EMERGENCY_CRITICALITY_THRESHOLD}: "
            "emergency override forces local EDGE processing; AHP not evaluated.",
            **base,
        )
    if inp.predicted_latency_ms is None:
        return DecisionResult(
            destination="EDGE",
            reason="prediction_unavailable_safe_default",
            veto="missing_prediction",
            edge_score=None,
            cloud_score=None,
            normalised={},
            explanation="No latency forecast available; routed to EDGE as the safe default.",
            **base,
        )
    if check_network_veto(inp.predicted_latency_ms):
        return DecisionResult(
            destination="EDGE",
            reason="network_degradation_veto",
            veto="network",
            edge_score=None,
            cloud_score=None,
            normalised={},
            explanation=f"Predicted latency {inp.predicted_latency_ms:.1f} ms >= {LATENCY_VETO_MS} ms: "
            "cloud path considered unreliable; EDGE forced.",
            **base,
        )

    n = normalise(inp.criticality, inp.predicted_latency_ms, inp.cloud_cost_index)
    edge_c = {
        "criticality": w["criticality"] * n["criticality"] ** 2,
        "latency": w["latency"] * n["latency"],
        "cost": w["cost"] * n["cost"],
    }
    cloud_c = {
        "criticality": w["criticality"] * (1 - n["criticality"]) ** 2,
        "latency": w["latency"] * (1 - n["latency"]),
        "cost": w["cost"] * (1 - n["cost"]),
    }
    edge, cloud = sum(edge_c.values()), sum(cloud_c.values())
    dest = "EDGE" if edge >= cloud else "CLOUD"
    diff = {k: edge_c[k] - cloud_c[k] for k in edge_c}
    driver = max(diff, key=lambda k: abs(diff[k]) if (diff[k] >= 0) == (dest == "EDGE") else -1)
    return DecisionResult(
        destination=dest,
        reason="ahp_decision",
        veto="none",
        edge_score=round(edge, 6),
        cloud_score=round(cloud, 6),
        normalised={k: round(v, 6) for k, v in n.items()},
        contributions={
            "edge": {k: round(v, 6) for k, v in edge_c.items()},
            "cloud": {k: round(v, 6) for k, v in cloud_c.items()},
        },
        explanation=f"AHP score EDGE {edge:.3f} vs CLOUD {cloud:.3f}; {dest} chosen, mainly driven by {driver}.",
        **base,
    )


def route_decision(
    device_id: str, patient_criticality_score: float, predicted_latency_ms: float, current_cloud_cost_index: float
) -> dict:
    """Backwards-compatible wrapper with the original function signature and keys."""
    r = decide(DecisionInput(device_id, patient_criticality_score, predicted_latency_ms, current_cloud_cost_index))
    return {
        "device_id": r.device_id,
        "routing_decision": r.destination,
        "reason": r.reason,
        "cloud_score": r.cloud_score,
        "edge_score": r.edge_score,
    }
