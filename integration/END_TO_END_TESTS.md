# End-to-end tests

## Automated (run on every `pytest`)
`tests/integration/test_api_pipeline.py::test_full_pipeline_routine_reading_goes_to_cloud` and
`::test_emergency_vitals_trigger_override_alert_and_delivery_log` exercise the whole chain with the **committed trained model**:

1. `POST /api/v1/events` with a device JWT → 201;
2. Charles: `prediction.method == "lstm"` (asserted whenever artifacts are present);
3. Tanmay: destination, reason, scores and weights present and consistent;
4. Rani: execution `success`, output reference written, alert created and **delivered** through a fake channel with an attempt row;
5. `GET /api/v1/events/{id}` returns the stored trace; audit chain verifies; dashboard summary reconciles
   (`test_dashboard_counts_reconcile_with_records`);
6. Restart: `tests/integration/test_persistence_and_migrations.py::test_records_survive_application_restart`.

## Manual demonstration script (what the faculty can watch, ~5 minutes)
```bash
uvicorn backend.app:create_app --factory --port 8000           # terminal 1
python -m scripts.stream_events --mode replay --count 50 --rate 2       # terminal 2: real data
python -m scripts.stream_events --mode simulate --scenario emergency --count 3
python -m scripts.stream_events --mode simulate --scenario degraded  --count 3
python -m scripts.stream_events --mode simulate --scenario failure   --count 2
```
Open http://localhost:8000 → Overview (counts move), Live events (click a row → full trace), Alerts (delivery log),
Audit → *Verify chain*, Model & data (real dataset + test metrics). Stop and restart terminal 1 → all records are still there.

## Recorded run
`reports/ROUTING_EVALUATION_REPORT.md` §1 and `results/routing/evidence_run_summary.json` (467 events over HTTP);
screenshots in `results/screenshots/`.
