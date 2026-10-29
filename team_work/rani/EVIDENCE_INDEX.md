# Rani — evidence index
| Claim | Evidence |
|---|---|
| 122 tests pass | `results/tests/pytest_output.txt` |
| PostgreSQL works, migrations clean | `results/tests/postgres_smoke.txt` |
| Persistence across restart (PostgreSQL container recreated) | `results/tests/infrastructure_runs.md` |
| Docker image builds and serves API + UI | `results/tests/infrastructure_runs.md` |
| Live run over HTTP, reconciliation, alert delivery | `results/routing/evidence_run_summary.json`, `results/logs/*.log` |
| Load test | `results/load/*.json`, `reports/SECURITY_AND_TEST_REPORT.md` §4 |
| Deadlock found and fixed | commit "fix lock-ordering deadlock", `tests/integration/test_concurrency.py` |
| UI reads real data | `results/screenshots/00_…11_*.png` |
| ER diagram | `architecture/ER_Diagram.png`, `integration/DATABASE_SCHEMA.md` |
| Security controls | `team_work/rani/SECURITY_NOTES.md` |
