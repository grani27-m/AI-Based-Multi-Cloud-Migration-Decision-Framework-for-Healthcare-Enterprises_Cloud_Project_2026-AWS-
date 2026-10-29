# Tanmay — module inventory

| Canonical path | Status | Lines of responsibility |
|---|---|---|
| `src/decision/ahp.py` | rewritten from original (method changed to exact eigenvector; validation added) | weights, CR, weight sets, report |
| `src/decision/override_rules.py` | kept, extended (network veto helper, env thresholds) | Stage A vetoes |
| `src/decision/router.py` | rewritten around the original formula | contract, validation, explanation, legacy wrapper |
| `src/decision/criticality.py` | new | partial NEWS2 criticality from vitals |
| `infra/aws/lambda_decision/handler.py` | replaces root `lambda_handler.py` (which wrapped the whole old pipeline) | Lambda entry point |
| `backend/routers/dashboard.py::decision_preview` | new endpoint (Rani's router, Tanmay's engine) | what-if API |
| `frontend/src/pages/DecisionLab.tsx` | rewritten | what-if UI + AHP verification table |
| `results/routing/weight_set_sensitivity.json` | new evidence | weight-set impact |
| Removed duplicate | `src/backend/decision/*` (identical copy) | kept in baseline commit `b825c85` |
