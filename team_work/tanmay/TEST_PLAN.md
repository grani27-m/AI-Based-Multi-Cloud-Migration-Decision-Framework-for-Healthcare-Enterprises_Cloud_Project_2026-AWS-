# Tanmay — test plan (all automated, `pytest tests/unit/test_decision.py tests/unit/test_lambda_handler.py`)

| Area | Tests |
|---|---|
| AHP maths | eigenvector weights = 0.6370/0.2583/0.1047; λmax 3.0385; CR 0.0332 (RI 0.58) and 0.037 (RI 0.52); weights sum to 1 for every set |
| Report discrepancy | reported C1 weight differs from both computed methods; latency weight matches |
| Matrix validation | non-reciprocal, non-square, non-unit diagonal, negative entries rejected; inconsistent matrix (CR ≥ 0.1) rejected |
| Emergency override | criticality 9.0 / 9.5 / 10 → EDGE for every latency/cost combination |
| Network veto | 300 / 450 / 5000 ms → EDGE; boundaries 8.99 and 299.99 fall through to AHP |
| Missing forecast | → EDGE, reason `prediction_unavailable_safe_default` |
| Invalid inputs | empty id, <0, >10, NaN, string, bool, negative latency, cost > 1 → `DecisionInputError` |
| Known cases | routine (0.9, 33.8 ms) → CLOUD; serious (7, 80 ms) → EDGE |
| Explainability | contributions sum to the scores; explanation + engine version present |
| Properties | monotonic in criticality (never EDGE→CLOUD as criticality rises); deterministic |
| Legacy API | `route_decision()` keeps the original keys |
| Criticality | partial NEWS2 cases incl. the aggregate-7 ↔ override equivalence; implausible vitals rejected |
| Lambda | direct invoke, API-Gateway proxy event, 422 on bad input |
