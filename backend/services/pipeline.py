"""
backend/services/pipeline.py  —  Owner: Rani Gupta
===================================================
End-to-end orchestration for ONE telemetry event. It calls the real modules of
the other two members; no prediction or AHP logic is re-implemented here.

    validate -> persist event (status=received, committed first so failures stay visible)
             -> Charles: LatencyPredictor.predict()           -> predictions
             -> Tanmay : criticality_from_vitals() + decide()   -> routing_decisions
             -> Rani   : Executor.execute()                     -> execution_records
             -> alerts (triggered here, delivered by services/alerts.py)
             -> audit chain entries for every step
             -> event status = completed | failed

Idempotency: event_id is UNIQUE. Re-sending the same event_id returns the stored
result with duplicate=true and does not predict/route/execute again.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.audit import write_audit
from backend.models import (Alert, Device, ExecutionRecord, Prediction, RoutingDecision, TelemetryEvent)
from backend.schemas import EventIn
from backend.security import Principal
from src.decision.criticality import criticality_from_vitals
from src.decision.router import DecisionInput, DecisionInputError, decide
from src.execution.adapters import Executor
from src.prediction.predict_service import LatencyPredictor, PredictionInputError, validate_window

log = logging.getLogger("pipeline")


class PipelineError(RuntimeError):
    def __init__(self, status_code: int, message: str, event_id: str | None = None):
        super().__init__(message)
        self.status_code, self.message, self.event_id = status_code, message, event_id


@dataclass
class PipelineContext:
    session_factory: object      # Database.session context manager
    predictor: LatencyPredictor
    executor: Executor


def _window_dicts(body: EventIn) -> list[dict]:
    return [{**o.model_dump(), "timestamp": o.timestamp.isoformat()} for o in body.network_window]


def event_result(db: Session, ev: TelemetryEvent, duplicate: bool = False) -> dict:
    p, d = ev.prediction, ev.decision
    ex = db.execute(select(ExecutionRecord).where(ExecutionRecord.telemetry_event_id == ev.id)
                    .order_by(ExecutionRecord.id.desc())).scalars().first()
    alerts = db.execute(select(Alert).where(Alert.telemetry_event_id == ev.id)).scalars().all()
    return {
        "event_id": ev.event_id, "duplicate": duplicate, "status": ev.status, "error": ev.error,
        "device_id": ev.device_id, "source": ev.source, "observed_at": ev.observed_at.isoformat(),
        "received_at": ev.received_at.isoformat(),
        "criticality": {"score": ev.criticality, "method": ev.criticality_method, "vitals": ev.vitals},
        "cloud_cost_index": ev.cloud_cost_index,
        "prediction": None if p is None else {
            "predicted_rtt_ms": p.predicted_rtt_ms, "risk": p.risk, "method": p.method,
            "model_version": p.model_version, "horizon_s": p.horizon_s, "inference_ms": p.inference_ms,
            "last_observed_rtt_ms": p.last_observed_rtt_ms},
        "decision": None if d is None else {
            "destination": d.destination, "reason": d.reason, "veto": d.veto, "edge_score": d.edge_score,
            "cloud_score": d.cloud_score, "weight_set": d.weight_set, "weights": d.weights,
            "normalised": d.normalised, "contributions": d.contributions, "engine_version": d.engine_version,
            "explanation": d.explanation},
        "execution": None if ex is None else {
            "status": ex.status, "requested_destination": ex.requested_destination,
            "final_destination": ex.final_destination, "adapter": ex.adapter, "attempts": ex.attempts,
            "duration_ms": ex.duration_ms, "output_ref": ex.output_ref, "error": ex.error,
            "attempt_log": ex.attempt_log},
        "alerts": [{"id": a.id, "severity": a.severity, "kind": a.kind, "status": a.status} for a in alerts],
    }


def process_event(ctx: PipelineContext, body: EventIn, principal: Principal) -> tuple[dict, list[int]]:
    """Returns (result dict, ids of alerts that must be dispatched)."""
    window = _window_dicts(body)
    # ---- cheap validation BEFORE anything is written --------------------------------------
    try:
        validate_window(window)
        crit = criticality_from_vitals(**body.vitals.model_dump()) if body.vitals else None
    except (PredictionInputError, ValueError) as exc:
        raise PipelineError(422, str(exc))
    score = crit.score if crit else float(body.criticality)
    method = crit.method if crit else "provided_by_client"
    event_id = body.event_id or uuid.uuid4().hex
    observed = body.observed_at or body.network_window[-1].timestamp
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)

    # ---- step 1: persist the event (own transaction) --------------------------------------
    try:
        with ctx.session_factory() as db:
            existing = db.execute(select(TelemetryEvent).where(TelemetryEvent.event_id == event_id)).scalar_one_or_none()
            if existing is not None:
                return event_result(db, existing, duplicate=True), []
            dev = db.get(Device, body.device_id)
            now = datetime.now(timezone.utc)
            if dev is None:
                db.add(Device(id=body.device_id, kind=body.device_kind, first_seen_at=now, last_seen_at=now))
            else:
                if not dev.is_active:
                    raise PipelineError(409, f"device {body.device_id} is deactivated")
                dev.last_seen_at = now
            ev = TelemetryEvent(
                event_id=event_id, device_id=body.device_id, source=body.source, observed_at=observed,
                criticality=score, criticality_method=method,
                vitals=({**body.vitals.model_dump(), "news2_points": crit.points} if crit else None),
                cloud_cost_index=body.cloud_cost_index, network_window=window,
                last_rtt_ms=next((o["rtt_avg_ms"] for o in reversed(window) if o["rtt_avg_ms"] is not None), None),
                provenance=body.provenance, status="received", submitted_by=principal.user_id)
            db.add(ev)
            db.flush()
            write_audit(db, principal.username, "event_received", f"event/{event_id}",
                        {"device_id": body.device_id, "source": body.source})
    except IntegrityError:  # concurrent duplicate of the same event_id
        with ctx.session_factory() as db:
            ev = db.execute(select(TelemetryEvent).where(TelemetryEvent.event_id == event_id)).scalar_one()
            return event_result(db, ev, duplicate=True), []

    # ---- steps 2-5: predict, decide, execute, alert ---------------------------------------
    alert_ids: list[int] = []
    try:
        with ctx.session_factory() as db:
            ev = db.execute(select(TelemetryEvent).where(TelemetryEvent.event_id == event_id)).scalar_one()
            pr = ctx.predictor.predict(window)                                         # Charles
            prow = Prediction(telemetry_event_id=ev.id, **pr.to_dict())
            db.add(prow)
            db.flush()
            dr = decide(DecisionInput(device_id=ev.device_id, criticality=score,       # Tanmay
                                      predicted_latency_ms=pr.predicted_rtt_ms,
                                      cloud_cost_index=body.cloud_cost_index))
            drow = RoutingDecision(telemetry_event_id=ev.id, prediction_id=prow.id, destination=dr.destination,
                                   reason=dr.reason, veto=dr.veto, edge_score=dr.edge_score,
                                   cloud_score=dr.cloud_score, weight_set=dr.weight_set, weights=dr.weights,
                                   normalised=dr.normalised, contributions=dr.contributions,
                                   engine_version=dr.engine_version, explanation=dr.explanation)
            db.add(drow)
            db.flush()
            payload = {"event_id": event_id, "device_id": ev.device_id, "criticality": score,
                       "vitals": body.vitals.model_dump() if body.vitals else None, "network_window": window,
                       "predicted_rtt_ms": pr.predicted_rtt_ms, "reason": dr.reason,
                       "simulate_failure": body.simulate_failure}
            out = ctx.executor.execute(dr.destination, payload)                        # Rani
            db.add(ExecutionRecord(telemetry_event_id=ev.id, decision_id=drow.id, **out.to_dict()))

            alerts = []
            if dr.reason == "override_critical_patient":
                alerts.append(("CRITICAL", "emergency_override",
                               f"EMERGENCY: device {ev.device_id} criticality {score:.1f}/10 - processed at EDGE. "
                               f"Predicted RTT {pr.predicted_rtt_ms:.1f} ms. Event {event_id}."))
            elif dr.reason == "network_degradation_veto":
                alerts.append(("WARNING", "network_veto",
                               f"Network degradation: predicted RTT {pr.predicted_rtt_ms:.1f} ms for device "
                               f"{ev.device_id}; routed to EDGE. Event {event_id}."))
            if out.status == "failed":
                alerts.append(("CRITICAL", "execution_failure",
                               f"EXECUTION FAILED for device {ev.device_id} ({dr.destination}): {out.error}"))
            for sev, kind, msg in alerts:
                a = Alert(telemetry_event_id=ev.id, device_id=ev.device_id, severity=sev, kind=kind, message=msg)
                db.add(a)
                db.flush()
                alert_ids.append(a.id)
                write_audit(db, "pipeline", "alert_triggered", f"alert/{a.id}", {"severity": sev, "kind": kind})

            ev.status = "completed" if out.status != "failed" else "failed"
            ev.error = None if out.status != "failed" else "execution failed"
            write_audit(db, "pipeline", "event_processed", f"event/{event_id}", {
                "prediction_id": prow.id, "predicted_rtt_ms": pr.predicted_rtt_ms, "prediction_method": pr.method,
                "model_version": pr.model_version, "decision_id": drow.id, "destination": dr.destination,
                "reason": dr.reason, "engine_version": dr.engine_version, "execution_status": out.status,
                "final_destination": out.final_destination})
            db.flush()
            result = event_result(db, ev)
    except (PredictionInputError, DecisionInputError) as exc:
        _mark_failed(ctx, event_id, f"invalid input: {exc}")
        raise PipelineError(422, str(exc), event_id)
    except Exception as exc:
        log.exception("pipeline failure for %s", event_id)
        _mark_failed(ctx, event_id, f"internal error: {type(exc).__name__}")
        raise PipelineError(500, "pipeline failed; the event was stored with status=failed", event_id)
    return result, alert_ids


def _mark_failed(ctx: PipelineContext, event_id: str, error: str) -> None:
    with ctx.session_factory() as db:
        ev = db.execute(select(TelemetryEvent).where(TelemetryEvent.event_id == event_id)).scalar_one_or_none()
        if ev is not None:
            ev.status, ev.error = "failed", error[:500]
            write_audit(db, "pipeline", "event_failed", f"event/{event_id}", {"error": error[:200]})
