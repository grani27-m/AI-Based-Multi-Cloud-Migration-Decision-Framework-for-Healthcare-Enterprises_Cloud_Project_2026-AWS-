# Final implementation status (2026-10-29)

Legend: **Verified** = implemented and demonstrated by a test or recorded run · **Partial** · **Blocked** (needs access we did not
have) · **Not done**.

## 1. Requirements matrix

| # | Requirement | Status | Evidence | Owner |
|---|---|---|---|---|
| 1 | Real RIPE Atlas data, provenance, checksums, rebuild commands | **Verified** | 756,495 raw results, manifest, `verify` 336/336; `DATASET_REPORT.md` | Charles |
| 2 | Real healthcare data (BIDMC) | **Verified** | 53 records, PhysioNet checksums 53/53 | Charles |
| 3 | No fabricated features | **Verified** | bandwidth/signal removed; `test_no_bandwidth_or_signal_strength_invented` | Charles |
| 4 | Chronological splits, no leakage, scaler on train | **Verified** | `ripe_atlas_splits.json`; `test_windows_never_cross_split_or_gap` | Charles |
| 5 | LSTM trained on real data, artifacts versioned | **Verified** | `models/latency_lstm/`, experiment log | Charles |
| 6 | Beat persistence baseline (report Objective 1) | **Verified** | test MAE 1.307 vs 1.633 ms, RMSE 6.515 vs 7.994 ms | Charles |
| 7 | Training / predicted-vs-actual graphs | **Verified** | `results/model/*.png`, dashboard | Charles |
| 8 | AHP weights + CR verified | **Verified** (with documented discrepancy) | 0.6370/0.2583/0.1047, CR 0.0332; report values not reproducible, impact 0.12 % | Tanmay |
| 9 | Safety vetoes + safe default + input validation | **Verified** | 37 decision tests | Tanmay |
| 10 | Explainable decisions | **Verified** | contributions + explanation stored per event; Decision Lab | Tanmay |
| 11 | One backend calling the real predictor and decision engine | **Verified** | `pipeline.py`; e2e tests assert `method=lstm` | Rani |
| 12 | Persistent database, migrations from empty DB | **Verified** (SQLite + PostgreSQL 16) | migration tests, `postgres_smoke.txt` | Rani |
| 13 | Persistence across restart | **Verified** | test + PostgreSQL container recreated | Rani |
| 14 | Idempotency | **Verified** | duplicate `event_id` → stored result, no re-execution | Rani |
| 15 | Edge/cloud execution, retries, fallback | **Verified** (local adapters) | execution tests, 10 fallback runs in evidence | Rani |
| 16 | JWT + RBAC (valid/invalid/expired, role matrix) | **Verified** | 29 auth tests | Rani |
| 17 | Audit hash chain + tamper detection | **Verified** | edit/delete/reorder/insert tests; verify endpoint | Rani |
| 18 | Alert attempts vs delivery recorded | **Verified** | delivery log tests; 12/12 webhook deliveries to a local receiver | Rani |
| 19 | Real Telegram / e-mail delivery | **Blocked** | needs bot token / Gmail app password (code + tests ready) | Rani |
| 20 | Dashboard reads only the API; counts reconcile | **Verified** | screenshots, reconciliation test and panel | Rani |
| 21 | Load test with percentiles (Objective 3) | **Partial** | p95 23–39 ms for 1 sender, 203 ms at 10 (PostgreSQL), fails above on a 2-vCPU host | Rani |
| 22 | MQTT ingestion | **Partial** | bridge + test without broker; broker run not recorded | Rani |
| 23 | Docker image + Compose | **Verified** (image build + container runs); full `docker compose up` not run here | `infrastructure_runs.md` | Rani |
| 24 | CI workflow | **Partial** | written; every job's commands run locally and pass; not yet run on GitHub | Rani |
| 25 | AWS deployment | **Prepared, not executed** | eu-north-1 plan, templates and staged guide `docs/AWS_DEPLOYMENT.md`; the team runs every command with their own least-privilege identity; nothing deployed until then | All |
| 26 | Member folders with ownership + evidence | **Verified** | `team_work/*`, `.github/CODEOWNERS` | All |
| 27 | Multi-cloud (several providers) | **Partial** | `src/decision/candidates.py` ranks EDGE vs N cloud destinations (139 tests incl. 126-case equivalence with `decide()`), `POST /api/v1/decision/rank`, Multi-cloud page; candidate latencies other than the measured LSTM forecast are hypothetical — no second provider is measured | Tanmay |
| 28 | ECG classification (PTB-XL) | **Not in scope** | not an objective in the report | — |
| 29 | Each member's part runnable on its own | **Verified** | `standalone_demos/{charles,tanmay,rani}` copied outside the repo, fresh venvs: 25+1 skipped / 184 / 69 tests pass, all numbered scripts exit 0; `*/TEST_REPORT.md`, `results/tests/standalone/` | All |
| 30 | One dashboard presenting the whole project | **Verified** | React Project tour, Request trace and Multi-cloud pages, all data from the API; `results/screenshots/final/` | Rani |
| 31 | Alert testing without real e-mails | **Verified** | `ALERT_MOCK_FILE` channel, status `mock_delivered` never counted as delivered; tests | Rani |

## Test totals at the time of this update
Main repository: **274 passed** (`python -m pytest -q`). Standalone packages: Charles 25 passed + 1 skipped (TensorFlow absent), Tanmay 184, Rani 69.

## 2. Open issues
1. One unexplained `NoResultFound` in an early PostgreSQL concurrency run (not reproduced in 4 reruns).
2. Throughput plateaus at ~55–68 req/s on the 2-vCPU sandbox; not profiled.
3. Network veto and emergency override never fire on the real data used (no RTT ≥ 300 ms in replayed windows; BIDMC partial NEWS2 ≤ 6); they are demonstrated with labelled simulations and tests.
4. The CI workflow has not run on GitHub yet; the first push will show whether the runner environment matches.

## 3. Old claims corrected
| Old claim (report / repo) | Verified fact |
|---|---|
| "Trained on 2,830,022 real RIPE Atlas measurements" | No data or model existed. Now: 756,495 raw / 753,410 clean real results, trained model in the repo |
| 5 features incl. bandwidth & signal strength | These were computed from RTT by formula; removed. 5 network features are RTT avg/min/max, jitter, loss (+ 2 time features) |
| Weights 0.6396 / 0.2583 / 0.1021, CR 0.037 | Eigenvector 0.6370 / 0.2583 / 0.1047, CR 0.0332 (0.037 only with RI 0.52) |
| "99 tests passing in CI" | No log existed and the suite could not run. Now 122 tests, log committed |
| 518 events / 32 alerts sent | Counting defects; replaced by reconciliation and triggered/delivered accounting |
| Predictions shown on the dashboard | Were `last × 1.1`; now LSTM, method stored per prediction |

## 4. Sections of the PDF report the team must update
* **Abstract, §3 Objective 1, §9.1, §13.1:** dataset size, "trained" wording, test results (MAE/RMSE table from `MODEL_EVALUATION_REPORT.md`).
* **§6 Dataset table:** size 30 MB raw / 756,495 rows; 2 measurements, 20 probes with data (19 usable), dates; feature list; BIDMC now "used" (criticality); licence lines filled.
* **§3/§9 AHP weights:** use the verified numbers and add the one-paragraph discrepancy note.
* **§8.2 Tools:** FastAPI 0.162, SQLAlchemy 2.1, PostgreSQL 16/SQLite, TensorFlow 2.21 (training only), React 19 + Vite; Streamlit + Plotly only for the three standalone member dashboards; no Redis/MLflow.
* **§10 Tests:** T04 now passes (reconciliation), T05/T06 verified by tests, T07 delivery log (webhook evidence; Telegram/e-mail blocked), T08 = 122 tests, T09 load test numbers, T10 concurrency test.
* **§10.3 Baselines:** forecaster baselines now evaluated; routing baselines partly (`ROUTING_EVALUATION_REPORT.md` §4).
* **§11 Limitations:** add the dormant-veto finding and the AI-assisted integration statement (`TEAM_CONTRIBUTIONS.md`).
* **§9.2 Figures:** replace Figures 4–7 with `results/screenshots/*` and `architecture/Implemented_Architecture.png`, `ER_Diagram.png`.
