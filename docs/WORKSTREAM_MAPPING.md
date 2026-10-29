# Workstream mapping (A–E)

The project is divided into five workstreams. Each row points to **real files in this repository** and to the standalone
package where that work can be run on its own. Ownership follows `reports/TEAM_CONTRIBUTIONS.md` and `.github/CODEOWNERS`.
Note: this integrated version was produced with AI assistance (see `reports/TEAM_CONTRIBUTIONS.md`); each member must be
able to run and explain the files mapped to them.

| WS | Workstream | Lead | Standalone package |
|---|---|---|---|
| **A** | Prediction & data pipeline | Charles Jehanabad (24BIT0522) | `standalone_demos/charles/` |
| **B** | Decision engine | Tanmay Kapoor (24BIT0079) | `standalone_demos/tanmay/` |
| **C** | Execution & security | Rani Gupta (24BIT0543) | `standalone_demos/rani/` |
| **D** | API, dashboard & monitoring | Rani Gupta (lead); Charles and Tanmay own the UI pages of their modules | `standalone_demos/rani/` (+ each member's Streamlit dashboard) |
| **E** | Deployment, integration & reporting | Rani Gupta (lead for Docker/CI/AWS); all members for reports | repository root |

## A — Prediction & data pipeline (Charles)
| Part | Files | Verify |
|---|---|---|
| RIPE Atlas download, manifest, checksums | `data_ingestion/ripe_atlas.py`, `dataset/config/ripe_atlas_selection.json`, `dataset/metadata/ripe_atlas_raw_manifest.jsonl`, `dataset/raw/ripe_atlas/` | `charles/01_inspect_datasets.py` |
| PhysioNet BIDMC download + criticality input | `data_ingestion/physionet_bidmc.py`, `dataset/raw/physionet_bidmc/`, `dataset/metadata/bidmc_quality.json` | `charles/01_inspect_datasets.py` |
| Parsing, cleaning, features, chronological windows | `src/prediction/ripe_parser.py`, `src/prediction/features.py`, `src/prediction/dataset.py`, `dataset/metadata/ripe_atlas_splits.json` | `charles/02_validate_and_preprocess.py` |
| LSTM model, training, model selection | `src/prediction/model.py`, `src/prediction/train.py`, `models/latency_lstm/`, `results/model/experiments/` | `charles/03_train_or_load_model.py [--train]` |
| Evaluation vs baselines | `src/prediction/evaluate.py`, `results/model/metrics.json`, `results/model/*.png` | `charles/04_evaluate_predictions.py` |
| Serving (NumPy inference used by the API) | `src/prediction/predict_service.py` | `tests/unit/test_prediction.py` |
| Replay of real data / labelled simulator | `data_ingestion/replay.py`, `data_ingestion/simulator.py`, `dataset/samples/` | `rani/03_run_execution_demo.py` |
| Reports | `reports/DATASET_REPORT.md`, `reports/MODEL_EVALUATION_REPORT.md` | — |
| Dashboard | `standalone_demos/charles/05_dashboard.py`; React `frontend/src/pages/ModelData.tsx` | `streamlit run 05_dashboard.py` |

## B — Decision engine (Tanmay)
| Part | Files | Verify |
|---|---|---|
| AHP weights, λmax, CI, CR | `src/decision/ahp.py` | `tanmay/02_calculate_ahp.py` |
| Safety vetoes (emergency, network, missing forecast) | `src/decision/override_rules.py` | `tests/unit/test_decision.py` |
| Two-stage router + explanations | `src/decision/router.py` | `tanmay/04_explain_decision.py` |
| Criticality from vital signs (partial NEWS2) | `src/decision/criticality.py` | `tanmay/04_explain_decision.py --vitals …` |
| Multi-cloud candidate ranking | `src/decision/candidates.py`, `POST /api/v1/decision/rank` | `tanmay/03_compare_candidates.py`, `tests/unit/test_candidates.py` |
| AWS Lambda wrapper | `infra/aws/lambda_decision/handler.py` | `tests/unit/test_lambda_handler.py` |
| Routing evaluation | `results/routing/`, `reports/ROUTING_EVALUATION_REPORT.md` | — |
| Dashboards | `standalone_demos/tanmay/05_dashboard.py`; React `DecisionLab.tsx` (UI by Rani for Tanmay's engine) | `streamlit run 05_dashboard.py` |

## C — Execution & security (Rani)
| Part | Files | Verify |
|---|---|---|
| Edge/cloud adapters, retry, CLOUD→EDGE fallback, S3 adapter | `src/execution/adapters.py` | `rani/03_run_execution_demo.py` |
| Pipeline orchestration, idempotency | `backend/services/pipeline.py` | `tests/integration/test_api_pipeline.py` |
| JWT, password hashing, roles | `backend/security.py`, `backend/deps.py`, `backend/routers/auth.py` | `tests/unit/test_auth.py` |
| Hash-chained audit log | `backend/audit.py` | `rani/04_inspect_audit_logs.py --tamper-demo` |
| Alerts + delivery log (Telegram, SMTP, webhook, SNS, mock) | `backend/services/alerts.py` | `tests/unit/test_audit_alerts_execution.py` |
| Security notes | `team_work/rani/SECURITY_NOTES.md`, `reports/SECURITY_AND_TEST_REPORT.md` | — |

## D — API, dashboard & monitoring (Rani lead)
| Part | Files | Verify |
|---|---|---|
| FastAPI app, config, metrics, health/ready | `backend/app.py`, `backend/config.py`, `backend/metrics.py`, `backend/schemas.py` | `rani/02_start_backend.py`, `/docs` |
| Routers | `backend/routers/{events,records,dashboard,auth}.py` | `integration/API_CONTRACT.md` |
| Database + migrations | `backend/models.py`, `backend/db.py`, `migrations/`, `alembic.ini` | `rani/01_initialize_database.py`, `rani/06_persistence_check.py` |
| React portal | `frontend/src/` (Project tour, Overview, Live events, Request trace, Devices, Alerts, Decision lab, Multi-cloud, Model & data, Audit, System, Admin) | `results/screenshots/final/` |
| Operations dashboard | `standalone_demos/rani/05_dashboard.py` | `streamlit run 05_dashboard.py` |
| Monitoring / ingestion | `monitoring/prometheus.yml`, `monitoring/mosquitto.conf`, `scripts/mqtt_bridge.py`, `scripts/load_test.py`, `results/load/` | — |

## E — Deployment, integration & reporting
| Part | Files | Owner |
|---|---|---|
| Container + compose | `Dockerfile`, `docker-compose.yml`, `.dockerignore` | Rani |
| CI | `.github/workflows/ci.yml`, `.github/CODEOWNERS` | Rani |
| AWS (eu-north-1) | `deploy/aws/` (bootstrap + app stacks, staged CloudShell scripts, server scripts, prod compose), `config/env/`, `docs/AWS_DEPLOYMENT.md`, `tests/unit/test_aws_deployment.py`; optional Lambda template `infra/aws/` | Rani (lead), run by the team |
| Integration docs | `integration/API_CONTRACT.md`, `integration/DATABASE_SCHEMA.md`, `integration/END_TO_END_TESTS.md` | Rani |
| Standalone export + sync check | `standalone_demos/export.py`, `tests/unit/test_standalone_sync.py` | All |
| Reports / status | `reports/FINAL_STATUS.md`, `reports/TEAM_CONTRIBUTIONS.md`, `INITIAL_PROJECT_AUDIT.md`, `architecture/` | All |
