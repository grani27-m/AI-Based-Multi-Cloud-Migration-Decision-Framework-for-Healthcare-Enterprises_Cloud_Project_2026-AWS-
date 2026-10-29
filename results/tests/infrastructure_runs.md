# Infrastructure runs (observed outputs, 2026-10-29, cloud sandbox: 2 vCPU, Linux, Python 3.13, Docker 29.9)

| Run | Command / setup | Observed result |
|---|---|---|
| Docker image build | `docker build -t hcf-api .` (multi-stage: node 22 → python 3.13-slim) | exit 0, image 892 MB |
| Container smoke (SQLite) | container + `/health`, `/ready`, login, `demo/run replay 5`, `GET /events` (SPA) | `ready:true, model_loaded:true`; 5 processed; dashboard HTML 200 |
| PostgreSQL 16 + restart | API container on `postgres:16-alpine`; 30 simulated events; **API container deleted and recreated** | after restart: 30 events, 30 predictions, 30 decisions, 30 executions, 4 alerts, 71 audit rows; reconciliation all true; chain valid |
| Alembic on PostgreSQL | upgrade → check → downgrade → upgrade | "No new upgrade operations detected" (see `postgres_smoke.txt`) |
| Concurrency (SQLite) | `tests/integration/test_concurrency.py`, 8 threads, 45 events, slow alert channel | passes; **fails on the pre-fix code** with `database is locked` after 30 s |
| Concurrency (PostgreSQL) | same scenario, 10 threads, 60 events, 4 repetitions | 60/60 completed, 20 alerts sent, chain valid in every repetition. One earlier attempt raised `NoResultFound` in a worker thread; it did not reproduce in 4 reruns and its cause is **not established** |
| Webhook delivery | `ALERT_WEBHOOK_URL` = local HTTP receiver (stand-in for Slack/Discord) | 12/12 emergency alerts delivered, HTTP 200, 11–21 ms each; payloads in receiver log |
| Telegram / e-mail / SNS | no credentials provided | not exercised against real providers; recorded as `skipped / channel not configured` |
