# API contract and member interfaces

Single source of truth: `backend/schemas.py` (Pydantic) for HTTP, `src/prediction/predict_service.py` and
`src/decision/router.py` (dataclasses) for in-process calls. Live OpenAPI docs: `http://localhost:8000/docs`.

## 1. The shared event (`POST /api/v1/events`)

```jsonc
{
  "event_id": "replay-1001-25250-1793183772-b07-212",   // optional idempotency key [A-Za-z0-9_.:-]{3,64}
  "device_id": "ICU-BIDMC-07",
  "device_kind": "bedside-monitor",
  "source": "replay",                // simulated | replay | live | test   (provenance class)
  "observed_at": "2026-10-23T09:16:12Z",   // optional, defaults to the last window timestamp
  "network_window": [                // EXACTLY 20 rounds, strictly increasing timestamps
    {"timestamp": "2026-10-23T08:00:12Z", "rtt_avg_ms": 41.2, "rtt_min_ms": 40.1,
     "rtt_max_ms": 43.0, "jitter_ms": 1.2, "loss_pct": 0.0}
    // rtt_* may be null only when loss_pct == 100
  ],
  "vitals": {"hr": 112, "resp": 24, "spo2": 93},   // XOR "criticality": 0-10
  "cloud_cost_index": 0.41,          // 0-1
  "provenance": {"network": "RIPE Atlas msm 1001, probe 25250, test period"},
  "simulate_failure": null           // "edge" | "cloud" | "both", only for source test/simulated
}
```

Validation (HTTP 422, nothing is stored): field ranges, 20 observations, ordering, `rtt_min ≤ rtt_avg ≤ rtt_max`,
exactly one of `vitals`/`criticality`, fault injection only for test/simulated data. Bodies above 256 KB → 413.

### Response (201 created, 200 duplicate)

```jsonc
{
  "event_id": "...", "duplicate": false, "status": "completed",      // completed | failed
  "criticality": {"score": 7.14, "method": "partial_news2_v1 (RR, SpO2, HR) - illustrative...", "vitals": {...}},
  "prediction": {"predicted_rtt_ms": 41.9, "risk": "LOW", "method": "lstm",
                 "model_version": "lstm-20261029-0518", "horizon_s": 240, "inference_ms": 1.1,
                 "last_observed_rtt_ms": 41.2},
  "decision": {"destination": "EDGE", "reason": "ahp_decision", "veto": "none",
               "edge_score": 0.41, "cloud_score": 0.38, "weight_set": "eigenvector",
               "weights": {"criticality": 0.637, "latency": 0.2583, "cost": 0.1047},
               "normalised": {...}, "contributions": {"edge": {...}, "cloud": {...}},
               "engine_version": "ahp-2stage-1.1", "explanation": "AHP score EDGE 0.410 vs CLOUD 0.380; ..."},
  "execution": {"status": "success", "requested_destination": "EDGE", "final_destination": "EDGE",
                "adapter": "local-edge-simulator", "attempts": 1, "duration_ms": 0.4,
                "output_ref": "file://2026-10-29.jsonl#...", "error": null, "attempt_log": [...]},
  "alerts": [{"id": 3, "severity": "CRITICAL", "kind": "emergency_override", "status": "triggered"}]
}
```

Error responses: `{"detail": "..."}` (+ `event_id` when the event was stored before the failure).
422 invalid input · 401 missing/invalid/expired token · 403 role not allowed · 409 deactivated device ·
413 body too large · 429 rate limit · 500 pipeline failure (the event row is kept with `status=failed`).

## 2. Member-to-member interfaces

### Charles → Tanmay/Rani — `LatencyPredictor.predict(window) -> PredictionResult`
* Input: the 20 `network_window` dicts above.
* Output: `predicted_rtt_ms`, `risk` (LOW < 75 ≤ MEDIUM < 150 ≤ HIGH), `method` (`lstm` | `persistence_fallback`),
  `model_version`, `horizon_s` (240), `inference_ms`, `last_observed_rtt_ms`.
* Errors: `PredictionInputError` (→ 422). Missing artifacts never raise: the predictor reports
  `method=persistence_fallback, model_version=none`, visible in the API, DB and dashboard.

### Tanmay → Rani — `decide(DecisionInput) -> DecisionResult`
* Input: `device_id`, `criticality` 0–10, `predicted_latency_ms` ≥ 0 or `None`, `cloud_cost_index` 0–1.
* Output: `destination` EDGE|CLOUD, `reason` (`override_critical_patient` | `network_degradation_veto` |
  `prediction_unavailable_safe_default` | `ahp_decision`), `veto`, scores, weights, contributions, `explanation`, `engine_version`.
* Errors: `DecisionInputError` (→ 422). A missing forecast is not an error: it yields EDGE (safe default).
* The same function is exposed read-only at `POST /api/v1/decision/preview` and as the AWS Lambda handler.

### Rani → frontend/database
* `Executor.execute(destination, payload) -> ExecutionOutcome` (`success` | `fallback_success` | `failed`).
* Persisted rows: `telemetry_events`, `predictions`, `routing_decisions`, `execution_records`, `alerts`,
  `alert_deliveries`, `audit_log` (see `DATABASE_SCHEMA.md`).

## 3. Endpoint list

| Method & path | Roles | Purpose |
|---|---|---|
| GET `/health`, `/ready`, `/metrics` | public | liveness, DB + model readiness, Prometheus |
| POST `/api/v1/auth/login` · GET `/api/v1/auth/me` | public · any | JWT login (60 min) |
| GET/POST `/api/v1/users` · PATCH `/api/v1/users/{id}` | admin | user management |
| POST `/api/v1/events` | admin, doctor, device | ingest → full pipeline |
| GET `/api/v1/events` (filters, pagination) · GET `/api/v1/events/{id}` | admin, doctor, auditor | history and full trace |
| GET `/api/v1/devices` · `/api/v1/executions` | admin, doctor, auditor | registry, execution history |
| GET `/api/v1/alerts` · POST `/api/v1/alerts/{id}/ack` | read: admin/doctor/auditor · ack: admin, doctor | alerts + delivery log |
| GET `/api/v1/audit` · `/api/v1/audit/verify` | admin, auditor | hash chain, verification |
| GET `/api/v1/dashboard/summary` · `/timeseries` | admin, doctor, auditor | aggregates + reconciliation |
| GET `/api/v1/system/info` | admin, doctor, auditor | model/dataset/AHP/AWS status |
| POST `/api/v1/decision/preview` | admin, doctor, auditor | what-if on the real engine (not stored) |
| POST `/api/v1/demo/run` | admin | push replay/simulated events through the pipeline |
