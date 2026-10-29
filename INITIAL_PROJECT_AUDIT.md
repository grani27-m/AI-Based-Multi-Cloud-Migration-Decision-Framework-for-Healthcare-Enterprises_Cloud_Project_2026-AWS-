# Initial project audit (state of the repository as received)

**Audited:** 2026-10-29 · **Input:** `AI-Based-…_Cloud_Project_2026-main.zip` (commit `b825c85` in this repository is a byte-for-byte import of that ZIP), the team report *AWS_Cloud_Project_Report_Filled (1)_final (1).pdf* (59 pp.), the two ChatGPT context bundles, the friend's *SentinelGraph* report (32 pp.) and four screenshots.
**Method:** every source file was read; duplicates were detected with `diff -rq`; the AHP numbers were recomputed; the original tests were not runnable as shipped (see §4). Statuses below describe the **received** code, not the final project. The final status is in [`reports/FINAL_STATUS.md`](reports/FINAL_STATUS.md).

## 1. Materials received and what could be accessed

| Item | Accessible | Notes |
|---|---|---|
| Repository ZIP (main) | yes | 196 files; also a second identical copy inside the chat bundle |
| GitHub URL | not cloned | the ZIP was used; the GitHub history (branches, PRs) was therefore **not** inspected |
| Team report PDF (59 pp.) | yes | read in full |
| `RIPE_Atlas_Chat_Bundle_1.zip` | yes | reconstructed transcript + 5 screenshots; candidate measurement 228839605 |
| `Cloud_Project_Chat_Bundle_1.zip` | yes | Rani README, audit checklist, test plan, dataset inventory, notes (checklists, not results) |
| Friend's SentinelGraph report (32 pp.) | yes | used only as a reference for depth and honesty of reporting |
| Screenshots (4) | yes | friend's folder tree, full-graph HTML explorer, literature-survey docx, papers folder |

## 2. Component audit

| Component | Existing files (as received) | Status | Evidence | Required change | Owner | Priority |
|---|---|---|---|---|---|---|
| RIPE Atlas dataset | `dataset/raw/.gitkeep`, `dataset/processed/.gitkeep`, `dataset/dataset_description.md` | **Missing** | both data folders contain only `.gitkeep`; no CSV/JSON anywhere; the 2,830,022 / 201 MB figures have no file, script output or log behind them | download real data, keep raw + manifest + checksums, document counts | Charles | P0 |
| RIPE downloader | `data_ingestion/ripe_atlas.py` | Partially implemented | fetched only the last 24 h of one ID; labelled built-in IDs 1001–1004 as Google/Cloudflare/AWS/Azure (unverified, wrong for 1001 = k-root); **fabricated `bandwidth_mbps` and `signal_strength_dbm` from RTT** with a formula; overwrote outputs | rewrite: configurable selection, chunked download, retries, no overwrite, SHA-256 manifest, measured fields only | Charles | P0 |
| PhysioNet BIDMC | `data_ingestion/physionet.py` | Implemented but unverified | never run; data absent; not connected to the pipeline | download with checksum check; use vitals for criticality | Charles | P1 |
| Training data | `src/prediction/data_generator.py` (+ duplicate in `src/ml_model/`) | Implemented (synthetic only) | 20,000 synthetic rows; this is what "trained" meant | replace with real RIPE data; keep a labelled simulator for demos | Charles | P0 |
| Preprocessing | `src/prediction/preprocessing.py` (+ duplicate) | Partially implemented | windows per device but the 80/20 split is over the concatenated array sorted by **device**, so "test" = the last devices, not the last time period (temporal leakage across devices); scaler fitted on the first 80 % of rows sorted by device; no validation split | chronological global cut-offs; whole window inside one split; scaler on train only | Charles | P0 |
| LSTM model | `src/prediction/model.py`, `train.py` (+ duplicates) | Implemented but unverified | architecture matches report (64→32 LSTM); **no `model.h5` exists** and none was ever committed | train on real data, save artifacts, evaluate vs baselines | Charles | P0 |
| Prediction service | `src/prediction/predict_service.py` (+ duplicate) | Partially implemented | without `model.h5` it silently returns `last_latency × 1.1` and still reports it as the model's output → every prediction shown in the report's dashboard came from this rule | explicit `method` field; persistence fallback labelled; input validation | Charles | P0 |
| Accuracy evidence | `results/accuracy.xlsx`, `results/*.png` | Not verifiable | no script produced them; report §10.2 says accuracy "not measured yet" | generate from held-out test set | Charles | P1 |
| AHP engine | `src/decision/ahp.py` (+ identical copy `src/backend/decision/`) | Implemented, numbers inconsistent | code uses column-normalisation → 0.6333/0.2605/0.1062; exact eigenvector → **0.6370/0.2583/0.1047**, CR 0.0332 (RI 0.58); report states 0.6396/0.2583/0.1021, CR 0.037 — C1/C3 not reproducible from the matrix by any standard method; 0.037 only with RI 0.52 | use the eigenvector (Saaty), keep the report's set selectable, document the discrepancy | Tanmay | P1 |
| Router / vetoes | `src/decision/router.py`, `override_rules.py` | Implemented, partially tested | no input validation (NaN, negative, >10 accepted); no behaviour for a missing forecast; docstring lists only 2 of 3 reasons | validation, safe EDGE default, explanation + contributions | Tanmay | P1 |
| Backend A | `src/api/main.py` (617 lines, SQLite) + identical copy `src/backend/APIs/main.py` | Implemented, prototype | used by Streamlit and the React portal; mock auth (in-memory UUID tokens, SHA-256 password, hard-coded `admin/hospital123`) | consolidate | Rani | P0 |
| Backend B | `backend/` (async FastAPI, PostgreSQL + Redis) | **Broken** | `POST /ingest` constructs `AuditLog(user_id=…, event_type=…, details=…, ip_address=…)` but the model has `ts/actor/action/detail/prev_hash/hash` → `TypeError` on every ingest; `backend/audit.py` is synchronous and unusable from the async app; hard dependency on Redis at startup | one backend; keep JWT/RBAC/hash-chain ideas | Rani | P0 |
| Database | `backend/models/*`, `migrations/versions/7880b038a2aa_initial_schema.py`, `src/execution/storage.py` | Partially implemented | two unrelated schemas (SQLite hot/cold tables vs PostgreSQL models); migration does not match the models (no audit hash columns) | single SQLAlchemy schema + Alembic migration verified with `alembic check` | Rani | P0 |
| Execution | `src/execution/edge_node.py`, `cloud_node.py` (+ copies in `src/aws/`) | Implemented (print + SQLite) | no failure handling/retries; edge "alert" is a `print` | adapters with retries, CLOUD→EDGE fallback, persisted outcome | Rani | P0 |
| Alerts | `backend/services/alert_service.py` (+ copy) | Partially implemented | Telegram/SMTP code exists; no delivery log; report counts **alerts sent = emergency overrides (32)** | per-attempt delivery records; triggered ≠ delivered | Rani | P1 |
| Audit chain | `backend/audit.py` (+ copy) | Implemented but unreachable | correct design, never called (ingest used the wrong model) | wire into every pipeline step; tamper tests | Rani | P1 |
| MQTT | `backend/mqtt/consumer.py`, `src/backend/mqtt/*` | Implemented but unverified | depends on the broken backend B | optional bridge into the same REST pipeline | Rani | P3 |
| React portal | `frontend/` | Partially implemented | builds; calls `/api/v1/*` of backend A; Model, Audit, Admin pages are placeholders; shows demo credentials | wire every page to the real API; remove credentials | Rani | P1 |
| Streamlit dashboard | `dashboard/app.py` + identical copy `src/frontend/app.py` | Implemented, prototype | reads the SQLite file directly (bypasses API/auth) | retire in favour of the React portal | Rani | P2 |
| Dashboard numbers | report Fig. 4–7 | Defect confirmed | 518 events vs 380+88+32 = 500 reasons; "Alerts 32" = overrides | reconciliation endpoint + test | Rani | P1 |
| Tests | `tests/test_*.py` (86 test functions) | Not runnable as shipped | import paths split across duplicates; CI expects Postgres + Redis services; "99/99 passing" in `PROJECT_COMPLETION_REPORT.md` has no log | new suite; record real runs | All | P0 |
| CI | `.github/workflows/ci.yml` | Partially implemented | lint + tests + docker build of files that are now duplicates | rewrite to the new layout | Rani | P2 |
| Docker | `Dockerfile.api`, `Dockerfile.mqtt`, `docker-compose.yml` (9 services) | Implemented but unverified | compose mounts `./monitoring/grafana/*` which does not exist; hard-coded DB password | single image + Postgres; secrets from `.env` | Rani | P2 |
| AWS | `lambda_handler.py` (+ copy) | Proposed only | nothing deployed (report says so) | IaC + deploy/teardown scripts; status file | All | P2 |
| Load test | `scripts/load_test.py` | Not run | report T09 "not run" | reproducible script + saved result | Rani | P2 |

## 3. Duplicated code (byte-identical unless noted)

`src/execution/auth.py` = `src/backend/Authentication/auth.py` · `src/api/main.py` = `src/backend/APIs/main.py` · `dashboard/app.py` = `src/frontend/app.py` · `backend/audit.py` = `src/aws/audit/audit.py` · `lambda_handler.py` = `src/aws/lambda_handler.py` · `src/execution/storage.py` = `src/backend/Database/storage.py` · `backend/services/alert_service.py` = `src/aws/alerts/alert_service.py` · `backend/core/security.py` = `src/backend/Authentication/security.py` · `backend/mqtt/consumer.py` = `src/backend/mqtt/consumer.py` · `backend/core/database.py` = `src/backend/Database/database.py` · `src/execution/edge_node.py` = `src/aws/edge_node/edge_node.py` · `src/ml_model/*` ≈ `src/prediction/*` and `src/decision/*` ≈ `src/backend/decision/*` (only the `__init__` comment differs). All duplicates were removed in the first restructuring commit; the originals remain in the baseline commit `b825c85`.

## 4. Baseline test run

The original suite could not be executed in a clean environment: `tests/test_api.py` imports the SQLite app while CI starts PostgreSQL/Redis for the other app; `tests/test_prediction.py` needs `data/processed/scaler.pkl` which never existed. No pre-existing log supports "99/99" or "55/55 passing". These claims are treated as unverified history.

## 5. Datasets required by the report

| Dataset | Required by | Present? | Action |
|---|---|---|---|
| RIPE Atlas ping measurements | report §6 (primary, training) | **No** | downloaded (see `reports/DATASET_REPORT.md`) |
| PhysioNet BIDMC | report §6 ("planned source of realistic vital signs") | No | downloaded, checksums verified, used for criticality |
| Simulated IoMT stream | report §6 (drives dashboard) | generator only | kept, labelled `source=simulated` |
| PTB-XL / ECG heartbeat | chat only, not in report | No | **out of scope**: the report has no ECG-classification objective; not implemented |
| Candidate msm 228839605 | chat screenshot | — | checked via API: 1 probe, 2-day campaign → unsuitable, rejected |

## 6. Scope decision: "multi-cloud migration"

The report (§1.4) says AWS is the target provider and multi-provider choice is "left as an extension". The implemented scope is therefore **predictive EDGE vs CLOUD routing on one provider**; cross-provider migration is not claimed.

## 7. Reference project comparison (SentinelGraph — reference only)

| Reference artifact | Purpose | Equivalent needed here | Status before | Action taken |
|---|---|---|---|---|
| Real public dataset (flaws.cloud CloudTrail, ~1.2 M events) | credibility of results | real RIPE Atlas + BIDMC | missing | 756,495 real ping results + 53 ICU records downloaded |
| Numbered pipeline scripts (`01_build…`, `02_graph_autoencoder…`, `05_full_graph.py`) | reproducibility | `data_ingestion/*`, `src/prediction/{dataset,train,evaluate}.py`, `make`-style commands in README | scattered | one command per stage |
| Held-out evaluation **with an honest baseline that beats the model on one metric** | honest reporting | LSTM vs persistence/EWMA/ridge on the same windows | none | `results/model/metrics.json`, experiment log incl. the failed first model |
| Interactive HTML graph explorer / dashboards | inspection of results | React portal on real API data | partial | all pages wired; per-event trace drawer |
| `AWS_DEPLOYMENT.md`, `run_aws_pipeline.py` | AWS plan separated from what was run | `infra/aws/*`, `reports/AWS_DEPLOYMENT_REPORT.md` | handler only | SAM template + deploy/teardown + status file |
| Dockerfile | portable run | Dockerfile + compose | broken compose | rebuilt and build-tested |
| Report wording "proposed rather than claimed as deployed" | honesty | status labels everywhere | mixed | `service_status.json`, FINAL_STATUS.md |

Nothing from SentinelGraph (graph schema, attack logic, AWS identifiers) was copied.
