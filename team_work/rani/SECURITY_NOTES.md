# Security notes — Rani Gupta (24BIT0543)

Implemented controls are listed with the test that proves them. This is a research prototype:
the controls are **HIPAA-aligned design choices, not a HIPAA certification or compliance claim.**

## Implemented and tested

| Control | Where | Test |
|---|---|---|
| Passwords hashed with PBKDF2-HMAC-SHA256, 16-byte salt, 310k iterations, constant-time compare | `backend/security.py` | `test_password_hash_roundtrip_and_salting` |
| Login does the same work for unknown users (no user-enumeration timing gap) | `routers/auth.py` (`_DUMMY_HASH`) | — (design) |
| JWT HS256 with `iss`, `aud`, `exp`, `iat`, `jti`; required claims enforced | `backend/security.py` | `test_expired_token_rejected`, `test_wrong_secret_or_audience_rejected`, `test_missing_malformed_and_tampered_tokens` |
| Deactivated users / changed roles lose access immediately (DB check on every request) | `backend/deps.py` | `test_deactivated_user_loses_access_immediately` |
| Role-based permissions in one table (`PERMISSIONS`) | `backend/security.py`, `deps.require()` | `test_role_matrix` (5 permissions × 4 roles = 20 cases) |
| Admin cannot lock themselves out | `routers/auth.py` | `test_admin_cannot_demote_self` |
| Input validation: types, ranges, window length/order, XOR vitals/criticality, fault flags only for test data | `backend/schemas.py` | `test_invalid_payloads_rejected_without_partial_writes` |
| Request body limit 256 KB → 413 | `backend/app.py` middleware | `test_oversized_body_rejected` |
| Per-user rate limit (default 600/min) → 429 | `backend/deps.py` | — (per-process; see limitations) |
| ORM only, no string-built SQL | all of `backend/` | — |
| Secrets only from environment; app refuses to start in production without `SECRET_KEY` | `backend/config.py` | — |
| No default/demo passwords anywhere (old `admin/hospital123` removed from code and UI) | `frontend/src/pages/SignIn.tsx`, `scripts/create_user.py` | — |
| Passwords never accepted as CLI arguments (getpass / env var) | `scripts/create_user.py` | — |
| Generic 500 responses with a request ID; stack traces only in server logs | `backend/app.py` | — |
| CORS restricted to configured origins; only GET/POST/PATCH; only `Authorization`, `Content-Type` headers | `backend/app.py` | — |
| `X-Content-Type-Options: nosniff`, `X-Request-ID` | `backend/app.py` | — |
| Token stored in `sessionStorage` (cleared when the tab closes) | `frontend/src/lib/api.ts` | — |
| Hash-chained, append-only audit for logins, failed logins, user changes, events, decisions, executions, alerts | `backend/audit.py` | `test_edited_row_detected`, `test_deleted_row_detected`, `test_reordered_rows_detected`, `test_inserted_forged_row_detected` |
| Audit detail never contains vitals, tokens or passwords | `services/pipeline.py` | `test_audit_detail_never_contains_vitals_or_tokens` |
| Alert-provider errors are sanitised before storage (tokens/passwords/webhook URL removed) | `services/alerts.py` | `test_secrets_are_sanitised_in_delivery_log` |
| Container runs as non-root user (uid 10001) | `Dockerfile` | build verified |
| Data minimisation: device IDs only, no names/MRNs; vitals = 3 numbers | `backend/models.py` | — |

## Known limitations (not hidden)

1. **Hash chain is tamper-evident, not tamper-proof.** A DB superuser can rewrite every row and recompute all hashes;
   deleting the *latest* rows is only detectable against an exported checkpoint. Mitigation: periodically store
   `head_hash` from `GET /api/v1/audit/verify` in a separate system (S3 Object Lock / CloudWatch Logs).
2. **No encryption at rest** for the local SQLite/PostgreSQL volumes. On AWS: RDS/S3 with KMS (S3 bucket in the
   template already uses SSE + public-access block).
3. **No TLS termination** in the local stack — put the API behind a TLS reverse proxy / API Gateway before any network exposure.
4. **Rate limiter is per process**; with several workers use a gateway limit (API Gateway throttling).
5. **No refresh tokens / revocation list**: logout is client-side; tokens expire after 60 min; deactivation is immediate.
6. **No MFA**; planned via Cognito.
7. **Mosquitto dev broker allows anonymous connections** (compose profile `mqtt` only). Production: password file + TLS or AWS IoT Core with X.509.
8. The criticality score is illustrative (partial NEWS2) — a safety-relevant parameter that needs clinical validation.

## Secret hygiene checklist
- `.env` is git-ignored; `.env.example` contains no values.
- `git log -p | grep -iE "password|token|secret"` on this repository shows only variable names and test fixtures.
- The original repository's `docker-compose.yml` contained `POSTGRES_PASSWORD: telemedicine123` and Grafana `admin123`;
  both were removed. If those values were ever used on a reachable server, rotate them.
