# Rani — test plan (all automated unless marked)
| Area | Tests |
|---|---|
| Auth | `tests/unit/test_auth.py` — hashing; login ok/fail; missing, malformed, tampered, expired, wrong-secret, wrong-audience tokens; deactivation; role matrix (20); ack permissions; self-demotion; user validation |
| Audit | `test_audit_alerts_execution.py` — intact, edited, deleted, reordered, inserted rows; no vitals/tokens in audit |
| Alerts | retry-then-deliver; all fail; partial; not configured; idempotent dispatch; secrets sanitised |
| Execution | edge + cloud write records; transient retry; cloud→edge fallback; edge failure stays failed; unknown destination |
| API e2e | `tests/integration/test_api_pipeline.py` — full pipeline, emergency + delivery, veto, idempotency, fallback, edge failure, invalid payloads (no partial writes), 413, reconciliation, audit, demo runs |
| Persistence/migrations | `test_persistence_and_migrations.py` — upgrade/check/downgrade from empty DB; restart persistence |
| Concurrency | `test_concurrency.py` — parallel ingest + alert dispatch |
| MQTT | `test_mqtt_bridge.py` — forward + dead-letter without a broker |
| Manual/recorded | PostgreSQL migrations + smoke + container restart; Docker build + container smoke; load tests; webhook delivery (`results/tests/infrastructure_runs.md`) |
