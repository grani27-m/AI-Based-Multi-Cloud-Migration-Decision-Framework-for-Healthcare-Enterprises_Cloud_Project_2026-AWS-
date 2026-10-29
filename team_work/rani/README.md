# Rani Gupta (24BIT0543) — Execution, backend integration, database, security, alerts, dashboard

**Role:** the layer that makes the other two modules *do* something: receive telemetry, call Charles's predictor and
Tanmay's decision engine, execute the decision, persist everything, audit it, alert people and show it in the UI.

## Canonical source

| Area | Files |
|---|---|
| API app & middleware | `backend/app.py` (factory, body-size guard, request IDs, metrics, SPA serving), `backend/config.py` |
| Contract | `backend/schemas.py` (Pydantic event/response models — see `integration/API_CONTRACT.md`) |
| Orchestration | `backend/services/pipeline.py` (validate → persist → predict → decide → execute → alert → audit) |
| Database | `backend/models.py` (9 tables), `backend/db.py`, `alembic.ini`, `migrations/` (`0001_initial_schema.py`) |
| Security | `backend/security.py` (PBKDF2, JWT, permission table), `backend/deps.py` (auth, RBAC, rate limit) |
| Audit | `backend/audit.py` (SHA-256 chain, verify) |
| Alerts | `backend/services/alerts.py` (Telegram, SMTP, webhook, SNS; attempt log; status machine) |
| Execution | `src/execution/adapters.py` (edge adapter, local object-store cloud adapter, S3 adapter, retrying executor with CLOUD→EDGE fallback) |
| Routers | `backend/routers/{auth,events,records,dashboard}.py` |
| Ops | `backend/metrics.py`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `monitoring/`, `scripts/{create_user,stream_events,load_test,smoke_test,mqtt_bridge}.py` |
| Frontend | `frontend/src/**` (React + Vite + Tailwind + Recharts; every page reads the API) |
| Tests | `tests/integration/*`, `tests/unit/test_auth.py`, `tests/unit/test_audit_alerts_execution.py` |

## Run
```bash
cp .env.example .env            # set SECRET_KEY, BOOTSTRAP_ADMIN_PASSWORD, DEVICE_PASSWORD
pip install -r requirements-dev.txt
uvicorn backend.app:create_app --factory --port 8000      # migrates the DB, creates the bootstrap admin
python -m scripts.create_user --username sim-device --role device --password-env DEVICE_PASSWORD
python -m scripts.stream_events --mode replay --count 100 --rate 5
cd frontend && npm ci && npm run dev                       # http://localhost:5173 (proxies to :8000)
# or everything in containers (PostgreSQL):  docker compose up --build  ->  http://localhost:8000
```

## What was wrong before, and what changed
| Before (verified in the received code) | Now |
|---|---|
| Two competing backends; the PostgreSQL one crashed on every `/ingest` (`AuditLog` built with non-existent fields) | One FastAPI app; 122 automated tests incl. end-to-end |
| Two unrelated schemas; migration did not match models | One schema, one Alembic migration, `alembic check` = no drift, tested upgrade/downgrade |
| Mock auth: in-memory UUID tokens, SHA-256 passwords, hard-coded `admin/hospital123` shown on the login page | JWT (iss/aud/exp), PBKDF2, 4 roles, permission table, no default credentials |
| Edge "alert" = `print()`; no failure handling | Adapters with retries, CLOUD→EDGE fallback, persisted attempt log, CRITICAL alert on EDGE failure |
| "Alerts sent" = number of overrides (32 in the report) | Triggered vs delivered vs failed vs not-configured, one row per channel attempt |
| Hash chain written but never reached | Every login/user change/event/decision/execution/alert is chained; verification endpoint + UI button |
| 518 events vs 500 reasons on the dashboard | Reconciliation block computed from the DB; tested; any mismatch is shown, not hidden |
| Streamlit read the SQLite file directly | React portal reads only through the authenticated API |

## Execution semantics
* EDGE → `local-edge-simulator` writes the processed record to `runtime/edge_buffer/<date>.jsonl` (stand-in for IoT Greengrass).
* CLOUD → `local-cloud-object-store` writes `runtime/cloud_objects/YYYY/MM/DD/<device>/<event>.json` (S3 key layout);
  `CLOUD_ADAPTER=s3` uses real S3 instead (needs credentials; not run in this environment).
* 3 attempts per destination; a failed CLOUD path falls back to EDGE (`fallback_success`); a failed EDGE path is **never**
  sent to the cloud — it is recorded as `failed` and raises a CRITICAL alert.

## Dependencies on the others
* **Charles:** `LatencyPredictor.load()` / `.predict()`; model artifacts in `models/latency_lstm/`; replay/simulator data sources.
* **Tanmay:** `decide()`, `criticality_from_vitals()`; the backend never re-implements AHP (the Decision Lab uses `/decision/preview`).

## Evidence
See `EVIDENCE_INDEX.md` — test logs, PostgreSQL run with an API restart, Docker build + container smoke test, load test, screenshots.

## Limitations
See `SECURITY_NOTES.md`. In short: no TLS/encryption-at-rest locally, per-process rate limit, tamper-evident (not tamper-proof)
audit, Telegram/e-mail delivery not exercised with real credentials (no credentials were provided; behaviour is tested with fake
channels and the "not configured" path is what the stored demo data shows), AWS services not deployed.

## Definition of done
- [x] One backend, one schema, migrations verified from an empty DB on SQLite **and PostgreSQL**
- [x] Persistence across an application restart (test + PostgreSQL container run)
- [x] Real predictor and real decision engine called in the pipeline (no hard-coded predictions)
- [x] Edge/cloud execution tested independently, with retries and fallback
- [x] JWT + RBAC with valid/invalid/expired/tampered tokens and a full role matrix
- [x] Audit tamper detection: edit, delete, reorder, insert
- [x] Alerts: success, retry-then-success, partial, all-fail, not-configured, idempotent dispatch, secret sanitisation
- [x] Dashboard counts reconcile with the database (test + UI panel)
- [x] Frontend reads only the API; loading/empty/error states; no demo credentials
- [x] Docker image builds and serves API + dashboard; load test recorded
- [ ] Real Telegram/e-mail delivery (needs bot token / app password)
- [ ] AWS deployment (needs account; `infra/aws/deploy.sh`)
