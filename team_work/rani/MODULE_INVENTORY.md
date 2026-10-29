# Rani — module inventory
| Path | Status vs received repo |
|---|---|
| `backend/app.py`, `config.py`, `db.py`, `deps.py`, `schemas.py` | new single backend (replaces `src/api/main.py` and the broken async `backend/`) |
| `backend/models.py` + `migrations/versions/0001_initial_schema.py` | new unified schema (9 tables) |
| `backend/security.py` | rewritten (PBKDF2 + PyJWT with iss/aud; old: python-jose/passlib in one app, SHA-256 + UUID tokens in the other) |
| `backend/audit.py` | kept design, made reachable and concurrency-safe |
| `backend/services/pipeline.py` | rewritten orchestration (old one crashed on AuditLog fields) |
| `backend/services/alerts.py` | rewritten with delivery log (old: booleans only) + webhook + SNS |
| `backend/routers/*` | auth, events, records, dashboard (incl. reconciliation, preview, demo) |
| `src/execution/adapters.py` | replaces `edge_node.py`, `cloud_node.py`, `storage.py`, `logger.py`, `auth.py` |
| `frontend/src/**` | kept design system/layout; all pages wired to the API; Model, Audit, Admin pages built (were placeholders) |
| `scripts/*` | create_user, stream_events, load_test, smoke_test, mqtt_bridge |
| ops | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.github/workflows/ci.yml`, `monitoring/*`, `infra/aws/*` |
| removed | duplicates under `src/backend`, `src/aws`, `src/api`, `src/frontend`, Streamlit `dashboard/` (direct DB access), `Dockerfile.api/.mqtt` |
