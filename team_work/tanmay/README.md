# Tanmay Kapoor (24BIT0079) — Decision layer: AHP / MCDM routing engine

**Role:** turn a latency forecast, a patient-criticality score and a cloud-cost index into an explainable EDGE/CLOUD decision,
with hard clinical-safety vetoes that no score can override.

## Canonical source (this folder only documents; code lives in one place)

| File | What it does |
|---|---|
| `src/decision/ahp.py` | pairwise matrix, principal-eigenvector weights (power iteration, pure Python), consistency index/ratio, matrix validation, weight sets, `ahp_report()` |
| `src/decision/override_rules.py` | Stage A vetoes: emergency (criticality ≥ 9.0), network (forecast ≥ 300 ms); thresholds from env |
| `src/decision/router.py` | `DecisionInput` → `decide()` → `DecisionResult` (destination, reason, veto, scores, contributions, explanation); input validation; safe default when no forecast; backward-compatible `route_decision()` |
| `src/decision/criticality.py` | partial NEWS2 (RR, SpO₂, HR) → 0–10 criticality from real BIDMC vitals |
| `infra/aws/lambda_decision/handler.py` | the same engine as an AWS Lambda / API Gateway handler |
| `tests/unit/test_decision.py`, `tests/unit/test_lambda_handler.py` | 40 tests |

## How to run / test
```bash
python -m src.decision.ahp                         # prints the verified AHP table (all three weight sets)
pytest tests/unit/test_decision.py tests/unit/test_lambda_handler.py -q
curl -X POST localhost:8000/api/v1/decision/preview -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"criticality":6,"predicted_latency_ms":80,"cloud_cost_index":0.4}'
```
The Decision Lab page of the dashboard calls the same endpoint interactively.

## Method
**Stage A — vetoes (no arithmetic):** criticality ≥ 9.0 → EDGE (`override_critical_patient`);
forecast missing → EDGE (`prediction_unavailable_safe_default`); forecast ≥ 300 ms → EDGE (`network_degradation_veto`).

**Stage B — AHP.** Pairwise matrix (Saaty scale): criticality vs latency 3, criticality vs cost 5, latency vs cost 3.

| Weight set | Criticality | Latency | Cost | CR |
|---|---|---|---|---|
| **Principal eigenvector (used)** | **0.6370** | **0.2583** | **0.1047** | **0.0332** (RI 0.58) / 0.0370 (RI 0.52) |
| Column normalisation (original code) | 0.6333 | 0.2605 | 0.1062 | 0.0334 |
| As printed in the report | 0.6396 | 0.2583 | 0.1021 | 0.037 |

The report's criticality and cost weights cannot be derived from its own matrix; its CR of 0.037 is the eigenvector CR with
the alternative random index 0.52. **Impact is negligible:** on an 11,880-point grid of non-veto inputs only 14 decisions
(0.12 %) differ between the report's weights and the eigenvector weights (`results/routing/weight_set_sensitivity.json`).
The report's set stays selectable with `AHP_WEIGHT_SET=report`.

Normalisation: n_c = criticality/10, n_l = min(latency/500 ms, 1), n_k = cost (0–1).
Scores (team design, kept): EDGE = w_c·n_c² + w_l·n_l + w_k·n_k; CLOUD = w_c·(1−n_c)² + w_l·(1−n_l) + w_k·(1−n_k).
The square makes moderately high criticality (≥ ~7) favour EDGE even on a good network; ties go to EDGE.
Every decision stores the per-criterion contributions, so the "why" can be shown afterwards.

## Inputs / outputs (contract)
See `integration/API_CONTRACT.md` §2. Invalid input (NaN, out of range, booleans, empty device id) raises
`DecisionInputError` → HTTP 422; it never produces a silent decision.

## Dependencies on the others
* **Charles** supplies `predicted_rtt_ms` (and whether it came from the LSTM or the labelled fallback).
* **Rani** calls `decide()` inside the pipeline, persists `DecisionResult`, executes the destination and raises alerts for vetoes.

## Limitations
* Thresholds (9.0, 300 ms) and weights are design parameters, not clinically validated.
* The squared-criticality aggregation is not standard additive AHP; it is documented as a design choice.
* Real RIPE Atlas data almost never reaches 300 ms (47 of 753,410 rounds), so on replayed real data the network veto is rare;
  its behaviour is demonstrated with the labelled `degraded` simulator scenario and unit tests.
* Multi-provider choice (the "multi-cloud" in the title) is not implemented; the AHP alternatives are EDGE and one CLOUD.

## Definition of done
- [x] AHP weights recomputed and verified; discrepancy with the report documented and quantified
- [x] CR computed and checked (< 0.10); inconsistent matrices rejected
- [x] Vetoes and safe default tested at and around their boundaries
- [x] Input validation with explicit errors
- [x] Explainable output (reason, scores, contributions, sentence)
- [x] Same code used by the API, the preview endpoint and the Lambda handler
- [x] Monotonicity and determinism tested
- [ ] Deployed to AWS Lambda (IaC ready in `infra/aws/`; needs an AWS account)
