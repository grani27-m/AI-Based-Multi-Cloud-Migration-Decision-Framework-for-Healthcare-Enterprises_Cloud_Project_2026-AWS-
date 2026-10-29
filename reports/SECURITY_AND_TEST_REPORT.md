# Security and test report

## 1. Automated test suite
* Command: `python -m pytest tests -v` · Environment: Python 3.13, Linux x86_64 · Result: **122 passed, 0 failed, 0 skipped**
  (full log with commit and date: `results/tests/pytest_output.txt`).
* Lint: `ruff check .` → all checks passed; `ruff format --check .` → clean.
* Frontend: `npm run build` (TypeScript strict + Vite) → success.

| File | Tests | Covers |
|---|---|---|
| `tests/unit/test_decision.py` | 37 | AHP maths and report discrepancy, matrix validation, vetoes and boundaries, safe default, invalid inputs, monotonicity, determinism, explanation, partial NEWS2 |
| `tests/unit/test_lambda_handler.py` | 3 | Lambda direct and API-Gateway invocation, 422 |
| `tests/unit/test_prediction.py` | 21 | RIPE parsing/derived fields, invalid records, no invented features, filling, time features, windows never cross split/gap, scaler, risk classes, **labelled fallback**, input validation, trained model loads, **numpy == Keras (1e-4)** |
| `tests/unit/test_auth.py` | 29 | hashing, login, missing/malformed/tampered/expired/wrong-audience tokens, deactivation, **role matrix (20 cases)**, ack permissions, self-demotion, user validation |
| `tests/unit/test_audit_alerts_execution.py` | 16 | chain intact / **edited / deleted / reordered / inserted**, no vitals or tokens in audit, alert retry-then-deliver, all-fail, partial, not-configured, idempotent dispatch, secret sanitisation, edge/cloud adapters, retries, fallback, EDGE never falls back to cloud |
| `tests/integration/test_api_pipeline.py` | 12 | end-to-end pipeline, emergency + delivery, network veto, **idempotency**, fallback, edge failure, invalid payloads without partial writes, 413, **dashboard reconciliation**, audit, demo replay/simulate |
| `tests/integration/test_persistence_and_migrations.py` | 2 | Alembic upgrade → check → downgrade from empty DB; **records survive an application restart** |
| `tests/integration/test_mqtt_bridge.py` | 1 | MQTT → REST forwarding and dead-lettering (no broker) |
| `tests/integration/test_concurrency.py` | 1 | parallel ingest + alert dispatch: no deadlock, linear audit chain |

## 2. Runs outside pytest
`results/tests/postgres_smoke.txt`, `results/tests/infrastructure_runs.md`: PostgreSQL 16 migrations + smoke test; data
surviving deletion and recreation of the API container; Docker image build and container smoke; concurrency on PostgreSQL;
webhook delivery of 12/12 emergency alerts to a local receiver.

## 3. Defect found and fixed during verification
**Lock-ordering deadlock (SQLite and, by the same pattern, PostgreSQL).** During the first live evidence run the streaming
client timed out. Cause: a background alert dispatch held SQLite's write lock (it had flushed delivery rows) and waited for the
process-wide audit lock, while a request thread held that audit lock and waited for SQLite → stalled until the 30 s busy
timeout. On PostgreSQL the same Python lock combined with the transaction-scoped advisory lock could deadlock the same way.
Fix (commit "fix lock-ordering deadlock"): SQLite transactions use `BEGIN IMMEDIATE`; the Python lock was removed; alert
dispatch never holds a transaction during network I/O; the auth dependency uses its own short session.
`test_concurrency.py` fails on the old code and passes on the fix.

Open item: one `NoResultFound` was raised once in a PostgreSQL concurrency run and did not reproduce in four reruns; root cause
not established (listed in FINAL_STATUS).

## 4. Load test (report Objective 3: p95 of ingestion < 200 ms)
`python -m scripts.load_test` — simulated events, unique IDs, client and server on the same 2-vCPU sandbox.

| Backend | Users × requests | Status codes | Throughput | p50 | **p95** | p99 |
|---|---|---|---|---|---|---|
| SQLite, 1 worker | 1 × 100 | 201 ×100 | 68 req/s | 13.2 ms | **22.6 ms** | 33.3 ms |
| SQLite, 1 worker | 10 × 30 | 201 ×300 | 64 req/s | 32.9 ms | **625.7 ms** | 1,464 ms |
| SQLite, 1 worker | 25 × 16 | 201 ×400 | 65 req/s | 172.2 ms | 1,310 ms | 2,419 ms |
| SQLite, 1 worker | 50 × 8 | 201 ×400 | 63 req/s | 542.8 ms | 1,529 ms | 3,097 ms |
| PostgreSQL 16, 4 workers (Docker) | 1 × 100 | 201 ×100 | 36 req/s | 26.6 ms | **38.8 ms** | 44.1 ms |
| PostgreSQL 16, 4 workers (Docker) | 10 × 30 | 201 ×300 | 58 req/s | 163.4 ms | **203.2 ms** | 215.4 ms |
| PostgreSQL 16, 4 workers (Docker) | 25 × 16 | 201 ×400 | 57 req/s | 371.0 ms | 729.8 ms | 859.2 ms |
| PostgreSQL 16, 4 workers (Docker) | 50 × 8 | 201 ×400 | 55 req/s | 587.7 ms | 1,688 ms | 2,525 ms |

**Objective 3 verdict:** met for a single stream (p95 23–39 ms), essentially at the limit for 10 concurrent senders on PostgreSQL
(203 ms), **not met** above that on this hardware. Throughput plateaus at ~55–68 req/s in every configuration, consistent with CPU
saturation of the 2-vCPU host that also runs the load generator; this was not profiled further. With the default limit of
600 requests/min per account, a 10-user run from one account returned 167 × HTTP 429
(`results/load/rate_limiter_check_10users.json`), which confirms the rate limiter; the capacity runs above raised the limit.

## 5. Security controls
See `team_work/rani/SECURITY_NOTES.md` for the full control table with the test proving each control, and the limitations
(no TLS or encryption at rest locally, tamper-evident not tamper-proof audit, per-process rate limit, no MFA).
**Compliance:** HIPAA-aligned design choices only; no certification or compliance is claimed.
