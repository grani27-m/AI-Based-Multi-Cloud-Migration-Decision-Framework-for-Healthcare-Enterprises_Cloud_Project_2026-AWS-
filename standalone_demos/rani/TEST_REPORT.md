# Test report — Rani's standalone package

**Run:** 29 Oct 2026, committed files copied **outside the repository**, new virtual environment, `pip install -r requirements.txt`.
Python 3.13.18, Linux x86_64; fastapi, SQLAlchemy, alembic, uvicorn 0.54.0, streamlit 1.66.1, pytest 9.2.0.
Logs (in the integrated repository): `results/tests/standalone/rani_flow.log`, `rani_pytest.log`, `rani_dashboard_apptest.log`,
`rani_server.log`. Generated passwords were not written to any log.

| Step | Result |
|---|---|
| `python 00_setup_env.py` | exit 0 — `.env` with random secrets |
| `python 01_initialize_database.py` | exit 0 — migrations applied, 9 tables, 3 users |
| `python 02_start_backend.py` | `/health` → `{"status":"ok","version":"2.0.0"}`, `/` (React build) → HTTP 200 |
| `python 03_run_execution_demo.py` | exit 0 — **14/14 checks passed** (emergency override, network veto, CLOUD→EDGE fallback, both adapters failing stored as `failed`, idempotency, 422 for invalid input and nothing stored, 401/403 for missing/forged tokens and wrong roles, audit chain valid) |
| `python 04_inspect_audit_logs.py` | exit 0 — hash chain VALID (59 entries), execution history and alert deliveries listed |
| `python 04_inspect_audit_logs.py --tamper-demo` | exit 0 — edit in a copy detected at the edited row; original untouched |
| `python 06_persistence_check.py` | exit 0 — **6/6 checks passed** across a process restart |
| `python -m pytest tests -q` | **69 passed** |
| `05_dashboard.py` (headless AppTest against the live API) | no exceptions, 6 tabs, hash chain VALID; screenshots `results/screenshots/final/standalone_rani_*.png` |
| React portal served by this package | screenshots `results/screenshots/final/*.png` (project tour, trace, multi-cloud, …), no browser errors |

Alerts in this run were **mock-delivered only** (local file); no real notification was sent. Edge/cloud adapters are local stand-ins.
PostgreSQL was not used in this package run (it is covered by the integrated project's PostgreSQL test log).
