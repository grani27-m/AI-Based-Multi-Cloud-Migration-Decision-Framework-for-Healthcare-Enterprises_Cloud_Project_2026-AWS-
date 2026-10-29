"""
01 - Show the decision criteria, units, normalisation, pairwise judgements and thresholds, and check
that data/criteria.json agrees with the constants in the code (src/decision/*).

    python 01_load_criteria.py
"""

from __future__ import annotations

from demo_common import load
from src.decision.ahp import CRITERIA, DEFAULT_PAIRWISE_MATRIX, REPORTED_CR, REPORTED_WEIGHTS
from src.decision.override_rules import EMERGENCY_CRITICALITY_THRESHOLD, LATENCY_VETO_MS
from src.decision.router import LATENCY_NORMALISATION_MS


def main() -> int:
    cfg = load("criteria.json")
    print("Criteria")
    for c in cfg["criteria"]:
        print(f"  {c['id']:<12} {c['name']:<28} unit: {c['unit']:<22} {c['normalisation']:<28} -> {c['favours']}")
    print("\nPairwise comparison matrix (Saaty 1-9 scale), rows/cols =", ", ".join(CRITERIA))
    for name, row in zip(CRITERIA, cfg["pairwise_matrix"]):
        print(f"  {name:<12}" + "".join(f"{v:>8.3f}" for v in row))
    t = cfg["thresholds"]
    print(f"\nThresholds: emergency criticality >= {t['emergency_criticality']}, network veto >= {t['latency_veto_ms']} ms, "
          f"CR limit < {t['cr_limit']}; latency normalised by {LATENCY_NORMALISATION_MS:.0f} ms")
    checks = {
        "matrix matches code": all(abs(a - b) < 1e-9 for r1, r2 in zip(cfg["pairwise_matrix"], DEFAULT_PAIRWISE_MATRIX) for a, b in zip(r1, r2)),
        "emergency threshold matches code": t["emergency_criticality"] == EMERGENCY_CRITICALITY_THRESHOLD,
        "veto threshold matches code": t["latency_veto_ms"] == LATENCY_VETO_MS,
        "reported weights recorded as in report": tuple(cfg["reported_weights"][k] for k in CRITERIA) == REPORTED_WEIGHTS
        and cfg["reported_weights"]["cr"] == REPORTED_CR,
    }
    print()
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
