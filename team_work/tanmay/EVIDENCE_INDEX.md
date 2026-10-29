# Tanmay — evidence index

| Claim | Evidence |
|---|---|
| Verified AHP weights and CR | `python -m src.decision.ahp` output; `tests/unit/test_decision.py::test_eigenvector_weights_match_verified_values` |
| Report weights not reproducible; impact 14/11,880 decisions | `results/routing/weight_set_sensitivity.json` |
| Engine is the one used in production paths | `backend/services/pipeline.py` imports `decide`; `infra/aws/lambda_decision/handler.py` imports `decide` |
| Decision distribution on real replayed data | `reports/ROUTING_EVALUATION_REPORT.md`, `results/routing/replay_run.json` |
| All tests pass | `results/tests/pytest_output.txt` |
| Screenshot | `results/screenshots/decision_lab.png` |
