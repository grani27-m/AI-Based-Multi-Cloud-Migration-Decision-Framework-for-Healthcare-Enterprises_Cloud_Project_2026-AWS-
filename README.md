# AI-Based Multi-Cloud Migration Decision Framework for Healthcare Enterprises

**BCSE355L Cloud Architecture Design · VIT Vellore · Team 11 · Course instructor: Dr. Priya V**

| Member | Reg. no. | Part | Folder |
|---|---|---|---|
| Charles Jehanabad | 24BIT0522 | Real datasets, preprocessing, LSTM latency prediction | [`team_work/charles`](team_work/charles/README.md) |
| Tanmay Kapoor | 24BIT0079 | AHP / MCDM decision engine, safety vetoes | [`team_work/tanmay`](team_work/tanmay/README.md) |
| Rani Gupta | 24BIT0543 | Execution, backend, database, security, alerts, dashboard, ops | [`team_work/rani`](team_work/rani/README.md) |

For every IoMT reading the system decides whether to process it at the **hospital edge** or in the **cloud**:

```
reading (20-round network window + vitals) ──► LSTM forecast of next RTT (Charles)
   ──► Stage A safety vetoes + Stage B AHP scoring (Tanmay)
   ──► edge / cloud execution with retry + fallback, persistence, hash-chained audit, alerts (Rani)
   ──► React dashboard reading the authenticated API
```

Research prototype — real public data, no patient identities, HIPAA-*aligned* design, not certified or clinically validated.
AWS services are designed and scripted but **not deployed** (see [`reports/AWS_DEPLOYMENT_REPORT.md`](reports/AWS_DEPLOYMENT_REPORT.md)).

## Verified results (details in `reports/`)

| | |
|---|---|
| Real network data | **756,495** RIPE Atlas ping results (msm 1001/1004, 20 Indian probes, 2 Sep – 28 Oct 2026) → 753,410 clean rows, SHA-256 manifest |
| Real vital signs | **53** PhysioNet BIDMC ICU recordings, checksums verified |
| Forecaster (held-out test, 113,077 windows) | **LSTM MAE 1.307 ms vs persistence 1.633 ms** (−20 %), RMSE 6.515 vs 7.994 ms |
| AHP weights (verified) | criticality 0.6370 · latency 0.2583 · cost 0.1047, CR 0.0332 |
| Tests | **122 passed** (unit + integration + e2e + concurrency), lint clean, frontend build OK |
| Database | SQLite and PostgreSQL 16, one Alembic migration, persistence across restart verified |
| Load (p95 of ingestion) | 23 ms (1 sender, SQLite) · 39 ms (1) / 203 ms (10 senders) on PostgreSQL, 4 workers, 2 vCPU |

Status of every requirement, including what is blocked or partial: [`reports/FINAL_STATUS.md`](reports/FINAL_STATUS.md).
What changed from the repository as received: [`INITIAL_PROJECT_AUDIT.md`](INITIAL_PROJECT_AUDIT.md).

## Quick start (local, SQLite, ~5 minutes)
Prerequisites: Python 3.11+ (tested 3.13), Node 20+ (tested 22).

```bash
cp .env.example .env
#   set SECRET_KEY (python -c "import secrets;print(secrets.token_hex(32))"),
#   BOOTSTRAP_ADMIN_PASSWORD and DEVICE_PASSWORD
pip install -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..          # the API serves the built dashboard
uvicorn backend.app:create_app --factory --port 8000      # migrates DB, creates admin
# second terminal:
python -m scripts.create_user --username sim-device --role device --password-env DEVICE_PASSWORD
python -m scripts.stream_events --mode replay --count 100 --rate 5        # real data
python -m scripts.stream_events --mode simulate --scenario emergency --count 3
```
Open **http://localhost:8000** (dashboard) and **http://localhost:8000/docs** (API). Frontend development with hot reload:
`cd frontend && npm run dev` → http://localhost:5173.

### With Docker (PostgreSQL)
```bash
cp .env.example .env     # also set POSTGRES_PASSWORD
docker compose up --build                 # http://localhost:8000
docker compose exec api python -m scripts.create_user --username sim-device --role device --password-env DEVICE_PASSWORD
```

### Tests
```bash
pytest -q                 # 122 tests, ~20 s, uses SQLite temp databases and the committed model
ruff check . && ruff format --check .
```

### Rebuild the data and the model from scratch
```bash
pip install -r requirements-train.txt
python -m data_ingestion.ripe_atlas download && python -m data_ingestion.ripe_atlas verify
python -m data_ingestion.physionet_bidmc download && python -m data_ingestion.physionet_bidmc build
python -m src.prediction.dataset build
python -m src.prediction.train --target-mode residual --loss huber --lr 1e-3 --epochs 20 --patience 3
python -m src.prediction.evaluate
```

## Repository map
| Path | Content |
|---|---|
| `data_ingestion/` | RIPE Atlas + BIDMC downloaders, real-data replay, labelled simulator |
| `src/prediction/` | parsing, features, splits, LSTM, training, evaluation, inference service |
| `src/decision/` | AHP, vetoes, router, partial-NEWS2 criticality |
| `src/execution/` | edge/cloud adapters, retrying executor |
| `backend/` | FastAPI app, schema, security, audit, alerts, pipeline, routers |
| `migrations/` | Alembic |
| `frontend/` | React dashboard |
| `dataset/`, `models/`, `results/` | data with provenance, trained model, evaluation, logs, screenshots, load tests |
| `infra/aws/` | SAM template, Lambda handler, deploy/teardown, service status |
| `integration/` | API contract, database schema + ER diagram, end-to-end tests |
| `reports/` | dataset, model, routing, security/test, AWS, contributions, final status |
| `team_work/` | one folder per member: README, module inventory, test plan, evidence index |
| `architecture/` | report figures + `Implemented_Architecture.png`, `ER_Diagram.png` |
| `docs/` | report documents, literature survey; `docs/archive/` = superseded drafts with unverified claims |

## Security
No credentials are stored in this repository; configuration comes from `.env` (git-ignored). See
[`team_work/rani/SECURITY_NOTES.md`](team_work/rani/SECURITY_NOTES.md) for controls, tests and limitations.

## How this version was produced
Integrated on 2026-10-29 with AI assistance from the team's repository and report; see
[`reports/TEAM_CONTRIBUTIONS.md`](reports/TEAM_CONTRIBUTIONS.md) and [`docs/GITHUB_PUBLISHING.md`](docs/GITHUB_PUBLISHING.md).

Data credits: RIPE NCC (RIPE Atlas); Pimentel et al. 2016 and PhysioNet (BIDMC, ODC-By 1.0).
