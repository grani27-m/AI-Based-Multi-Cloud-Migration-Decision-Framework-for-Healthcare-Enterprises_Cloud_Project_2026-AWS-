"""
03 - Run the decision engine on every cached pipeline event and on a multi-cloud example.

    python 03_compare_candidates.py

Part A recomputes the EDGE/CLOUD decision for 127 events exported from the integrated system
(data/sample_events.json - real LSTM forecasts / real BIDMC vitals for source=replay, simulated
inputs for source=simulated) and checks that this standalone engine reproduces every recorded
decision. Part B ranks an edge node against several clouds (data/candidates_example.json).
Writes results/fixture_decisions.csv and results/multi_cloud_ranking.json.
"""

from __future__ import annotations

import csv
import json
from collections import Counter

from demo_common import RESULTS, load
from src.decision.candidates import CloudCandidate, rank_candidates
from src.decision.router import DecisionInput, decide


def main() -> int:
    ev = load("sample_events.json")["events"]
    RESULTS.mkdir(exist_ok=True)
    rows, mismatches = [], 0
    for e in ev:
        r = decide(DecisionInput(e["device_id"], e["criticality"], e["predicted_latency_ms"], e["cloud_cost_index"]),
                   weight_set_name=e.get("recorded_weight_set", "eigenvector"))
        same = r.destination == e["recorded_destination"] and r.reason == e["recorded_reason"]
        mismatches += not same
        rows.append({"event_id": e["event_id"], "source": e["source"], "criticality": e["criticality"],
                     "predicted_latency_ms": e["predicted_latency_ms"], "cloud_cost_index": e["cloud_cost_index"],
                     "destination": r.destination, "reason": r.reason, "edge_score": r.edge_score,
                     "cloud_score": r.cloud_score, "matches_integrated_system": same})
    with open(RESULTS / "fixture_decisions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Part A - {len(rows)} cached events")
    print("  by source/destination/reason:", dict(Counter((r["source"], r["destination"], r["reason"]) for r in rows)))
    print(f"  recomputed decision == decision stored by the integrated system: {len(rows) - mismatches}/{len(rows)}")
    print("  first 8 rows:")
    for r in rows[:8]:
        print(f"    {r['event_id'][:38]:<38} crit {r['criticality']:>5.2f} lat {r['predicted_latency_ms']:>7.1f} ms "
              f"cost {r['cloud_cost_index']:.2f} -> {r['destination']:<5} {r['reason']}")

    ex = load("candidates_example.json")
    res = rank_candidates("example", ex["criticality"], [CloudCandidate(**c) for c in ex["clouds"]])
    print(f"\nPart B - multi-cloud ranking (HYPOTHETICAL inputs), criticality {ex['criticality']}")
    for s in res.ranking:
        print(f"  {s.name:<30} {s.kind:<5} " + (f"score {s.score:.4f}" if s.score is not None else f"excluded: {s.excluded_reason}"))
    print(f"  -> {res.destination}: {res.explanation}")
    (RESULTS / "multi_cloud_ranking.json").write_text(json.dumps(res.to_dict(), indent=2))
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
