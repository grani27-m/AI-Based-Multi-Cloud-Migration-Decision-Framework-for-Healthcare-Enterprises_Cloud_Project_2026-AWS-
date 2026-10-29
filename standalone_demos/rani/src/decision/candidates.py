"""
src/decision/candidates.py  —  Owner: Tanmay Kapoor
=====================================================
Multi-candidate extension of the decision engine: rank ONE edge node against ANY number of
cloud destinations (e.g. two AWS regions, or AWS vs another provider), each with its own
predicted latency and cost index. This is the "multi-cloud" part of the project title.

It reuses the same AHP weights, vetoes and score formula as router.py and is designed so that
with exactly one cloud candidate it returns the SAME destination and scores as decide()
(tested in tests/unit/test_candidates.py).

Rules
    Stage A  emergency (criticality >= 9.0)              -> EDGE
             a cloud candidate whose forecast >= 300 ms  -> excluded (network veto for that cloud)
             cloud candidate without a forecast          -> excluded (no blind routing)
             no cloud candidate left                     -> EDGE
    Stage B  EDGE  = w_c*n_c^2      + w_l*n_l(best cloud) + w_k*n_k(best cloud)
             CLOUD_i = w_c*(1-n_c)^2 + w_l*(1-n_l,i)      + w_k*(1-n_k,i)
             "best cloud" = the admissible cloud with the highest CLOUD score; the edge is compared
             with the best alternative it would otherwise lose the reading to.
Highest score wins; ties go to EDGE.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from src.decision.ahp import weight_set
from src.decision.override_rules import EMERGENCY_CRITICALITY_THRESHOLD, LATENCY_VETO_MS
from src.decision.router import ENGINE_VERSION, LATENCY_NORMALISATION_MS, WEIGHT_SET, DecisionInputError


@dataclass
class CloudCandidate:
    name: str  # e.g. "aws-eu-north-1"
    predicted_latency_ms: float | None
    cost_index: float  # 0-1

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise DecisionInputError("candidate name is required")
        if (
            not isinstance(self.cost_index, (int, float))
            or math.isnan(self.cost_index)
            or not 0 <= self.cost_index <= 1
        ):
            raise DecisionInputError(f"{self.name}: cost_index must be in [0, 1]")
        p = self.predicted_latency_ms
        if p is not None and (not isinstance(p, (int, float)) or math.isnan(p) or p < 0):
            raise DecisionInputError(f"{self.name}: predicted_latency_ms must be >= 0 or null")


@dataclass
class CandidateScore:
    name: str
    kind: str  # edge | cloud
    admissible: bool
    excluded_reason: str | None
    score: float | None
    contributions: dict = field(default_factory=dict)
    normalised: dict = field(default_factory=dict)


@dataclass
class RankingResult:
    device_id: str
    destination: str  # "EDGE" or a cloud candidate name
    destination_kind: str  # edge | cloud
    reason: str
    criticality: float
    weights: dict
    weight_set: str
    ranking: list  # list[CandidateScore] sorted best first
    explanation: str
    engine_version: str = ENGINE_VERSION + "+candidates"

    def to_dict(self) -> dict:
        return asdict(self)


def rank_candidates(
    device_id: str,
    criticality: float,
    clouds: list[CloudCandidate],
    weight_set_name: str | None = None,
) -> RankingResult:
    if not isinstance(device_id, str) or not device_id.strip():
        raise DecisionInputError("device_id is required")
    if (
        not isinstance(criticality, (int, float))
        or isinstance(criticality, bool)
        or math.isnan(criticality)
        or not 0 <= criticality <= 10
    ):
        raise DecisionInputError(f"criticality must be a number in [0, 10], got {criticality!r}")
    if not clouds:
        raise DecisionInputError("at least one cloud candidate is required")
    names = [c.name for c in clouds]
    if len(set(names)) != len(names) or "EDGE" in names:
        raise DecisionInputError("candidate names must be unique and must not be 'EDGE'")
    for c in clouds:
        c.validate()

    ws = weight_set(weight_set_name or WEIGHT_SET)
    w = ws["weights"]
    n_c = criticality / 10.0
    base = dict(device_id=device_id, criticality=criticality, weights=w, weight_set=ws["name"])

    if criticality >= EMERGENCY_CRITICALITY_THRESHOLD:
        edge = CandidateScore("EDGE", "edge", True, None, None)
        rest = [CandidateScore(c.name, "cloud", False, "emergency override", None) for c in clouds]
        return RankingResult(
            destination="EDGE",
            destination_kind="edge",
            reason="override_critical_patient",
            ranking=[edge, *rest],
            explanation=f"Criticality {criticality:.2f} >= {EMERGENCY_CRITICALITY_THRESHOLD}: emergency override, "
            "all cloud candidates skipped.",
            **base,
        )

    scored: list[CandidateScore] = []
    for c in clouds:
        if c.predicted_latency_ms is None:
            scored.append(CandidateScore(c.name, "cloud", False, "no latency forecast", None))
            continue
        if c.predicted_latency_ms >= LATENCY_VETO_MS:
            scored.append(
                CandidateScore(c.name, "cloud", False, f"network veto ({c.predicted_latency_ms:.0f} ms)", None)
            )
            continue
        n_l = min(c.predicted_latency_ms / LATENCY_NORMALISATION_MS, 1.0)
        n_k = min(max(c.cost_index, 0.0), 1.0)
        contrib = {
            "criticality": w["criticality"] * (1 - n_c) ** 2,
            "latency": w["latency"] * (1 - n_l),
            "cost": w["cost"] * (1 - n_k),
        }
        scored.append(
            CandidateScore(
                c.name,
                "cloud",
                True,
                None,
                round(sum(contrib.values()), 6),
                {k: round(v, 6) for k, v in contrib.items()},
                {"criticality": n_c, "latency": round(n_l, 6), "cost": n_k},
            )
        )

    admissible = [s for s in scored if s.admissible]
    if not admissible:
        reasons = "; ".join(f"{s.name}: {s.excluded_reason}" for s in scored)
        reason = (
            "network_degradation_veto"
            if all("veto" in (s.excluded_reason or "") for s in scored)
            else "prediction_unavailable_safe_default"
        )
        return RankingResult(
            destination="EDGE",
            destination_kind="edge",
            reason=reason,
            ranking=[CandidateScore("EDGE", "edge", True, None, None), *scored],
            explanation=f"No admissible cloud candidate ({reasons}); EDGE chosen.",
            **base,
        )

    best_cloud = max(admissible, key=lambda s: s.score)
    nl, nk = best_cloud.normalised["latency"], best_cloud.normalised["cost"]
    e_contrib = {"criticality": w["criticality"] * n_c**2, "latency": w["latency"] * nl, "cost": w["cost"] * nk}
    edge = CandidateScore(
        "EDGE",
        "edge",
        True,
        None,
        round(sum(e_contrib.values()), 6),
        {k: round(v, 6) for k, v in e_contrib.items()},
        {"criticality": n_c, "latency": nl, "cost": nk, "compared_with": best_cloud.name},
    )
    ranking = sorted([edge, *scored], key=lambda s: (s.score is not None, s.score or 0, s.kind == "edge"), reverse=True)
    winner = ranking[0]
    others = ", ".join(f"{s.name} {s.score:.3f}" for s in ranking[1:] if s.score is not None)
    excluded = [s for s in scored if not s.admissible]
    return RankingResult(
        destination=winner.name,
        destination_kind=winner.kind,
        reason="ahp_decision",
        ranking=ranking,
        explanation=f"{winner.name} has the highest AHP score {winner.score:.3f} (vs {others})"
        + (f"; excluded: {', '.join(f'{s.name} ({s.excluded_reason})' for s in excluded)}" if excluded else "")
        + ".",
        **base,
    )
