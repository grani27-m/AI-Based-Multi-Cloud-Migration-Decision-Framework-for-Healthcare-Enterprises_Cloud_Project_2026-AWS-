# Team contributions

## How this version was produced (please read before submitting)
The original repository (baseline commit `b825c85`) contains the team's own work as received. **This integrated version was
produced on 2026-10-29 with an AI assistant (Claude)** working from that repository, the team report and the chat bundles. The
commits after the baseline are authored "Team 11 (AI-assisted integration)" on purpose: they must not be presented as
commits written by any single member. Each member should read, run and be able to explain the files mapped to them below
before the review, and the course's academic-integrity rules on AI assistance apply. Commit/PR evidence for report §12.2
must come from the members' own GitHub activity (see `docs/GITHUB_PUBLISHING.md`).

## Ownership map (canonical files; each folder in `team_work/` documents one member)

| Member | Owns (canonical paths) | Member folder |
|---|---|---|
| **Charles Jehanabad (24BIT0522)** — datasets & prediction | `data_ingestion/` (RIPE Atlas, BIDMC, replay, simulator), `src/prediction/` (parser, features, dataset, model, train, evaluate, predict_service), `dataset/`, `models/latency_lstm/`, `results/model/`, `reports/DATASET_REPORT.md`, `reports/MODEL_EVALUATION_REPORT.md`, `tests/unit/test_prediction.py` | `team_work/charles/` |
| **Tanmay Kapoor (24BIT0079)** — decision engine | `src/decision/` (ahp, override_rules, router, criticality), `infra/aws/lambda_decision/`, `results/routing/`, `reports/ROUTING_EVALUATION_REPORT.md`, `frontend/src/pages/DecisionLab.tsx` (UI of his engine), `tests/unit/test_decision.py`, `tests/unit/test_lambda_handler.py` | `team_work/tanmay/` |
| **Rani Gupta (24BIT0543)** — execution, backend, DB, security, alerts, UI, ops | `src/execution/`, `backend/`, `migrations/`, `alembic.ini`, `frontend/` (all other pages), `scripts/`, `infra/aws/` (template, deploy), `monitoring/`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/`, `integration/`, `reports/SECURITY_AND_TEST_REPORT.md`, `reports/AWS_DEPLOYMENT_REPORT.md`, `tests/integration/*`, `tests/unit/test_auth.py`, `tests/unit/test_audit_alerts_execution.py` | `team_work/rani/` |
| All | `README.md`, `INITIAL_PROJECT_AUDIT.md`, `reports/FINAL_STATUS.md`, `architecture/`, literature survey and report documents in `docs/` | — |

The same mapping is enforced on GitHub by `.github/CODEOWNERS` (each owner is the required reviewer of their paths).

## Commit history in this repository
| Commit | Area |
|---|---|
| `b825c85` | baseline import of the repository ZIP (team's original work) |
| `e818524` | Charles — real data pipelines, features, splits, LSTM, numpy inference, evaluation |
| `684357a` | Tanmay — verified AHP, validation, safe default, explanations, criticality |
| `c092014` | Rani — backend, schema + migrations, execution, auth, audit, alerts |
| `d874cd2` | tests |
| `a038be3` | raw data |
| `7cdb36b` | Charles — selected model + experiment log |
| `be596ea` | Rani — React portal wired to the API |
| `eb58ad8` | ops & documentation |
| `b725e54` | Rani — deadlock fix + regression test |
| later | evidence, reports, member folders |
