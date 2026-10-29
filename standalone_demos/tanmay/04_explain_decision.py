"""
04 - Explain one decision in full (command-line).

    python 04_explain_decision.py --criticality 6.5 --latency 80 --cost 0.4
    python 04_explain_decision.py --vitals 118,24,93 --latency 80 --cost 0.4          # HR,RESP,SpO2 -> criticality
    python 04_explain_decision.py --criticality 3 --cloud "mumbai:30:0.5" --cloud "stockholm:150:0.2"   # multi-cloud
    python 04_explain_decision.py --criticality 3 --latency nan --cost 0.4            # invalid input -> explicit error
"""

from __future__ import annotations

import argparse

import demo_common  # noqa: F401
from src.decision.candidates import CloudCandidate, rank_candidates
from src.decision.criticality import criticality_from_vitals
from src.decision.router import DecisionInput, DecisionInputError, decide


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--criticality", type=float)
    g.add_argument("--vitals", help="HR,RESP,SpO2")
    ap.add_argument("--latency", type=str, default="40", help="predicted latency in ms, or 'none'")
    ap.add_argument("--cost", type=float, default=0.3)
    ap.add_argument("--cloud", action="append", help="name:latency_ms:cost (repeat for multi-cloud ranking)")
    ap.add_argument("--weight-set", default="eigenvector", choices=["eigenvector", "report", "column_normalisation"])
    a = ap.parse_args()
    try:
        if a.vitals:
            hr, rr, sp = (float(x) for x in a.vitals.split(","))
            c = criticality_from_vitals(hr, rr, sp)
            print(f"Vitals HR {hr} RR {rr} SpO2 {sp} -> partial NEWS2 points {c.points} = {c.aggregate} -> criticality {c.score}")
            print(f"  ({c.method})")
            crit = c.score
        else:
            crit = a.criticality
        if a.cloud:
            clouds = []
            for spec in a.cloud:
                name, lat, cost = spec.rsplit(":", 2)
                clouds.append(CloudCandidate(name, None if lat.lower() == "none" else float(lat), float(cost)))
            r = rank_candidates("cli", crit, clouds, weight_set_name=a.weight_set)
            print(f"\nWeights ({r.weight_set}): {r.weights}")
            for s in r.ranking:
                print(f"  {s.name:<20} {s.kind:<5} " + (f"score {s.score:.4f}  contributions {s.contributions}" if s.score is not None
                                                     else f"excluded: {s.excluded_reason}"))
            print(f"\nDECISION: {r.destination} ({r.reason})\n{r.explanation}")
            return 0
        lat = None if a.latency.lower() == "none" else float(a.latency)
        r = decide(DecisionInput("cli", crit, lat, a.cost), weight_set_name=a.weight_set)
    except (DecisionInputError, ValueError) as exc:
        print(f"REJECTED (explicit error, no decision made): {exc}")
        return 2
    print(f"\nWeights ({r.weight_set}): " + ", ".join(f"{k} {v:.4f}" for k, v in r.weights.items()))
    if r.veto != "none":
        print(f"Stage A veto fired: {r.veto}")
    else:
        print("Normalised inputs: " + ", ".join(f"{k} {v:.4f}" for k, v in r.normalised.items()))
        print(f"{'criterion':<12}{'EDGE':>10}{'CLOUD':>10}")
        for k in r.contributions["edge"]:
            print(f"{k:<12}{r.contributions['edge'][k]:>10.4f}{r.contributions['cloud'][k]:>10.4f}")
        print(f"{'total':<12}{r.edge_score:>10.4f}{r.cloud_score:>10.4f}")
    print(f"\nDECISION: {r.destination}  (reason: {r.reason})\n{r.explanation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
