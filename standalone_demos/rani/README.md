# Rani Gupta (24BIT0543) — Execution, security, backend, database & alerts (standalone demo)

This folder is a **complete, runnable backend** on its own: FastAPI API, persistent database with Alembic migrations,
JWT roles, execution adapters with retry and CLOUD→EDGE fallback, hash-chained audit log, alert delivery log and two
dashboards (the React portal served by the API, and a Streamlit operations view). It does not need Charles's or
Tanmay's folders: the parts of their modules that the backend calls (LSTM inference in NumPy, the AHP engine, the replay
data sample) are byte-identical copies listed in `EXPORTED_FILES.json`.

## What is real and what is a local stand-in
| Part | Status in this package |
|---|---|
| API, database, migrations, auth, audit chain, alert log | **real code, really running** |
| Replay events | **real data**: RIPE Atlas held-out test windows (sample `dataset/samples/ripe_atlas_test_sample.csv.gz`) + PhysioNet BIDMC vitals |
| Simulated events | **synthetic**, labelled `source=simulated` with the scenario in `provenance` |
| LSTM forecast | real trained model (`models/latency_lstm/weights.npz`, NumPy inference) |
| Edge node / cloud | **local stand-ins** `local-edge-simulator` and `local-cloud-object-store` (files under `runtime/`). `CLOUD_ADAPTER=s3` uses real Amazon S3 |
| Alerts | by default **mock** only: written to `runtime/mock_alerts.jsonl`, status `mock_delivered`, *nobody is notified*. Set Telegram/SMTP/webhook in `.env` for real delivery (`delivered`) |

## Clean-laptop launch sequence (Windows PowerShell; macOS/Linux identical except the activate line)
Python **3.11–3.13** (tested 3.13). Two terminals.

```powershell
cd rani
python -m venv .venv
.venv\Scripts\Activate.ps1                 # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python 00_setup_env.py                     # creates .env with random secrets, prints the demo passwords once
python 01_initialize_database.py           # Alembic migrations -> runtime/app.db, creates admin/doctor/sim-device
python 02_start_backend.py                 # terminal 1: API + React portal on http://127.0.0.1:8000  (Ctrl+C stops)
```
Terminal 2 (activate the same venv):
```powershell
python 03_run_execution_demo.py            # real replay + simulated scenarios + failures + invalid input + authz: 14 checks
python 04_inspect_audit_logs.py            # reads the DB directly: counts, audit chain, executions, alert deliveries
python 04_inspect_audit_logs.py --tamper-demo   # edits one audit row in a COPY of the DB -> detected
streamlit run 05_dashboard.py              # operations dashboard on http://localhost:8501 (uses the live API)
python 06_persistence_check.py             # starts its own server on :8011, stores, stops, restarts, verifies
python -m pytest tests -q                  # 69 tests
```
Open **http://127.0.0.1:8000** (React portal, log in with the `admin` password printed by step 00) and
**http://127.0.0.1:8000/docs** (interactive API documentation).

| Step | Script | What it proves |
|---|---|---|
| 00 | `00_setup_env.py` | no secrets in the code: `.env` is generated locally and git-ignored |
| 01 | `01_initialize_database.py` | migrations create all 9 tables; idempotent (run twice = same state) |
| 02 | `02_start_backend.py` | one process serves the API, `/health`, `/ready`, `/metrics` and the React build |
| 03 | `03_run_execution_demo.py` | emergency → EDGE override, degraded network → veto, cloud failure → fallback recorded, both adapters down → stored as `failed`, duplicate `event_id` → no second execution, invalid input → 422 and not stored, 401/403 for missing/forged tokens and wrong roles, audit chain valid |
| 04 | `04_inspect_audit_logs.py` | audit trail, execution history and every alert delivery attempt are in the database |
| 05 | `05_dashboard.py` | System · Send events · **Request flow** (clickable graph: device → API → telemetry row / LSTM → AHP decision → execution → alerts / audit entries, each node shows the stored data) · Executions · Alerts · Audit log |
| 06 | `06_persistence_check.py` | data, users and the audit chain survive a process restart |

## Using PostgreSQL instead of SQLite
`pip install psycopg2-binary`, then in `.env`: `DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/hcf` and run
01 again. The same migrations and tests run on PostgreSQL 16 (see the integrated project's CI and `results/tests/`).

## Tests (69)
`tests/unit` and `tests/integration` are the integrated project's backend tests (auth, roles, JWT expiry/forgery, audit
tamper detection, alert retries and statuses, execution retry/fallback, migrations, persistence, concurrent writers,
MQTT bridge). `tests/test_package.py` runs scripts 01, 03, 04, 05 (headless) and 06 against a temporary database and a
real server process.

## Relation to the integrated project
Everything except `00`–`06`, `demo_common.py`, `tests/test_package.py`, this README, `.env.example` and
`requirements.txt` is a byte-identical copy (`EXPORTED_FILES.json`). Change code in the main repository and re-export.

## Limitations
Edge and cloud are local stand-ins unless S3 is configured; real alert delivery needs your own Telegram/SMTP credentials;
SQLite is fine for a demo but a multi-user deployment should use PostgreSQL; throughput on a 2-vCPU laptop is
~55–68 events/s (see `results/load/` in the integrated project).
