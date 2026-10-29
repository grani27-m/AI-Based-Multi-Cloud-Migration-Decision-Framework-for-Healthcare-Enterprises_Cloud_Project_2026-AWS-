# Database schema

* **Engine:** SQLAlchemy 2.x ORM (`backend/models.py`), schema created only by Alembic (`migrations/versions/0001_initial_schema.py`).
* **Databases:** PostgreSQL 16 (Docker Compose — recommended, matches the report) and SQLite (zero-setup local runs, tests).
  Both are exercised: the automated suite runs on SQLite; the PostgreSQL run is recorded in `results/tests/postgres_smoke.txt`.
* **Initialisation:** the API runs `alembic upgrade head` at start-up (`AUTO_MIGRATE=true`), or manually:
  `DATABASE_URL=... alembic upgrade head`. `alembic check` confirms models and migrations agree (tested).

```mermaid
erDiagram
    users ||--o{ telemetry_events : submits
    users ||--o{ alerts : acknowledges
    devices ||--o{ telemetry_events : sends
    telemetry_events ||--|| predictions : "1 per event"
    telemetry_events ||--|| routing_decisions : "1 per event"
    predictions ||--|| routing_decisions : feeds
    routing_decisions ||--o{ execution_records : executes
    telemetry_events ||--o{ alerts : raises
    alerts ||--o{ alert_deliveries : "one row per channel attempt"

    users {
        int id PK
        string username UK
        string password_hash
        string role "admin|doctor|auditor|device"
        bool is_active
    }
    devices {
        string id PK
        string kind
        datetime first_seen_at
        datetime last_seen_at
        bool is_active
    }
    telemetry_events {
        int id PK
        string event_id UK "idempotency key"
        string device_id FK
        string source "simulated|replay|live|test"
        datetime observed_at
        float criticality "0-10"
        string criticality_method
        json vitals
        float cloud_cost_index "0-1"
        json network_window
        json provenance
        string status "received|completed|failed"
    }
    predictions {
        int id PK
        int telemetry_event_id FK
        float predicted_rtt_ms
        string risk
        string method "lstm|persistence_fallback"
        string model_version
        float inference_ms
    }
    routing_decisions {
        int id PK
        int telemetry_event_id FK
        int prediction_id FK
        string destination "EDGE|CLOUD"
        string reason
        string veto
        float edge_score
        float cloud_score
        json weights
        json contributions
        string engine_version
    }
    execution_records {
        int id PK
        int decision_id FK
        string requested_destination
        string final_destination
        string adapter
        string status "success|fallback_success|failed"
        int attempts
        json attempt_log
        float duration_ms
    }
    alerts {
        int id PK
        int telemetry_event_id FK
        string severity
        string kind
        string status "triggered|delivered|partially_delivered|failed|not_configured|not_notified"
        datetime delivered_at
    }
    alert_deliveries {
        int id PK
        int alert_id FK
        string channel
        int attempt
        string status "sent|failed|skipped"
        string detail
        float latency_ms
    }
    audit_log {
        int id PK
        string ts
        string actor
        string action
        string resource
        json detail
        string prev_hash
        string hash UK
    }
```

## Constraints and indexes
* CHECK: `criticality` 0–10, `cloud_cost_index` 0–1, `source` enum, `destination` EDGE/CLOUD, `role` enum.
* UNIQUE: `telemetry_events.event_id` (idempotency), one prediction and one decision per event, one alert per (event, kind), `audit_log.hash`.
* Indexes: event source/status/received_at/device, decision destination/reason/created_at, alert status/severity, audit actor/action.
* All timestamps are timezone-aware UTC; the UI converts to IST.

## Transactions and failure behaviour
1. The event row is committed **first** (`status=received`), so a later crash leaves visible evidence.
2. Prediction, decision, execution, alerts and audit entries are written in **one** transaction.
3. On any error the event is marked `status=failed` with a sanitised `error` and an `event_failed` audit entry.
4. Concurrent duplicates of the same `event_id` hit the UNIQUE constraint and are answered with the stored result.
5. Alert delivery runs after the commit (background task) and updates only the alert/delivery rows.

## Privacy
No names, MRNs or free text about patients are stored. Vitals are three numbers per event (needed to explain the
criticality score); audit `detail` never contains vitals (tested in `test_audit_detail_never_contains_vitals_or_tokens`).

## Backup / recovery
* PostgreSQL: `docker compose exec postgres pg_dump -U hcf hcf > backup.sql`; restore with `psql`. On AWS: RDS automated
  backups / PITR (not deployed).
* SQLite: stop the API and copy `runtime/app.db` (WAL mode: also copy `app.db-wal` if present).
* After restoring, run `GET /api/v1/audit/verify` and compare the head hash with the last exported checkpoint.
