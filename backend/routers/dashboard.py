"""Dashboard aggregates, system/model metadata and the demo runner.  Owner: Rani Gupta"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.deps import get_db, require
from backend.models import Alert, ExecutionRecord, Prediction, RoutingDecision, TelemetryEvent
from backend.routers.events import schedule_alerts
from backend.schemas import DemoRun, EventIn
from backend.security import Principal
from backend.services.pipeline import PipelineError, process_event
from src.decision.ahp import ahp_report
from src.decision.router import ENGINE_VERSION, REASONS, WEIGHT_SET, DecisionInput, DecisionInputError, decide
from src.decision.override_rules import EMERGENCY_CRITICALITY_THRESHOLD, LATENCY_VETO_MS

ROOT = Path(__file__).resolve().parents[2]
router = APIRouter(prefix="/api/v1", tags=["dashboard"])


def _counts(db: Session, col, *where):
    q = select(col, func.count()).group_by(col)
    for w in where:
        q = q.where(w)
    return {str(k): int(v) for k, v in db.execute(q).all()}


def _json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


class DecisionPreview(BaseModel):
    criticality: float = Field(..., ge=0, le=10)
    predicted_latency_ms: float | None = Field(None, ge=0, le=5000)
    cloud_cost_index: float = Field(..., ge=0, le=1)
    weight_set: str = Field("eigenvector", pattern="^(eigenvector|column_normalisation|report)$")


@router.post("/decision/preview")
def decision_preview(body: DecisionPreview, _: Principal = Depends(require("records:read"))):
    """Run Tanmay's real decision engine on hypothetical inputs. Nothing is stored or executed."""
    try:
        return decide(
            DecisionInput("preview", body.criticality, body.predicted_latency_ms, body.cloud_cost_index),
            weight_set_name=body.weight_set,
        ).to_dict()
    except DecisionInputError as exc:
        raise HTTPException(422, str(exc)) from exc


class CloudOption(BaseModel):
    name: str = Field(..., min_length=1, max_length=48)
    predicted_latency_ms: float | None = Field(None, ge=0, le=5000)
    cost_index: float = Field(..., ge=0, le=1)


class RankRequest(BaseModel):
    criticality: float = Field(..., ge=0, le=10)
    clouds: list[CloudOption] = Field(..., min_length=1, max_length=10)
    weight_set: str = Field("eigenvector", pattern="^(eigenvector|column_normalisation|report)$")


@router.post("/decision/rank")
def decision_rank(body: RankRequest, _: Principal = Depends(require("records:read"))):
    """Multi-cloud ranking: EDGE vs several cloud destinations (Tanmay's candidates.py). Not stored."""
    from src.decision.candidates import CloudCandidate, rank_candidates

    try:
        return rank_candidates(
            "preview",
            body.criticality,
            [CloudCandidate(c.name, c.predicted_latency_ms, c.cost_index) for c in body.clouds],
            weight_set_name=body.weight_set,
        ).to_dict()
    except DecisionInputError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/dashboard/summary")
def summary(
    source: Optional[str] = Query(None, description="filter: simulated|replay|live|test"),
    _: Principal = Depends(require("records:read")),
    db: Session = Depends(get_db),
):
    ev_filter = [TelemetryEvent.source == source] if source else []
    ev_ids = select(TelemetryEvent.id).where(*ev_filter) if source else select(TelemetryEvent.id)
    events_total = db.execute(select(func.count()).select_from(TelemetryEvent).where(*ev_filter)).scalar_one()
    by_status = _counts(db, TelemetryEvent.status, *ev_filter)
    by_source = _counts(db, TelemetryEvent.source, *ev_filter)
    dec_where = [RoutingDecision.telemetry_event_id.in_(ev_ids)]
    by_dest = _counts(db, RoutingDecision.destination, *dec_where)
    by_reason = _counts(db, RoutingDecision.reason, *dec_where)
    decisions_total = sum(by_dest.values())
    by_method = _counts(db, Prediction.method, Prediction.telemetry_event_id.in_(ev_ids))
    by_risk = _counts(db, Prediction.risk, Prediction.telemetry_event_id.in_(ev_ids))
    by_exec = _counts(db, ExecutionRecord.status, ExecutionRecord.telemetry_event_id.in_(ev_ids))
    al_where = [Alert.telemetry_event_id.in_(ev_ids)]
    alerts_by_status = _counts(db, Alert.status, *al_where)
    alerts_by_kind = _counts(db, Alert.kind, *al_where)
    alerts_total = sum(alerts_by_status.values())
    unknown_reasons = {k: v for k, v in by_reason.items() if k not in REASONS}
    pct = lambda n, d: round(100.0 * n / d, 1) if d else 0.0  # noqa: E731
    failed_before_decision = _failed_without_decision(db, ev_ids)
    in_flight = by_status.get("received", 0)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_filter": source or "all",
        "events": {"total": events_total, "by_status": by_status, "by_source": by_source},
        "decisions": {
            "total": decisions_total,
            "edge": {"count": by_dest.get("EDGE", 0), "pct": pct(by_dest.get("EDGE", 0), decisions_total)},
            "cloud": {"count": by_dest.get("CLOUD", 0), "pct": pct(by_dest.get("CLOUD", 0), decisions_total)},
            "by_reason": {r: by_reason.get(r, 0) for r in REASONS} | unknown_reasons,
        },
        "predictions": {"by_method": by_method, "by_risk": by_risk},
        "executions": {"by_status": by_exec},
        "alerts": {
            "triggered": alerts_total,
            "by_status": alerts_by_status,
            "by_kind": alerts_by_kind,
            "delivered": alerts_by_status.get("delivered", 0) + alerts_by_status.get("partially_delivered", 0),
            "failed": alerts_by_status.get("failed", 0),
            "not_configured": alerts_by_status.get("not_configured", 0),
            "mock_delivered": alerts_by_status.get("mock_delivered", 0),
            "pending": alerts_by_status.get("triggered", 0),
        },
        "reconciliation": {
            "events_equal_sum_of_statuses": events_total == sum(by_status.values()),
            "reasons_sum_equals_decisions": sum(by_reason.values()) == decisions_total,
            "events_equal_decisions_plus_failed_before_decision_plus_in_flight": events_total
            == decisions_total + failed_before_decision + in_flight,
            "failed_before_decision": failed_before_decision,
            "in_flight": in_flight,
            "note": "Events without a decision are those rejected/failed before routing or still being processed. "
            "Alerts 'delivered' counts only alerts with at least one successful channel delivery.",
        },
    }


def _failed_without_decision(db: Session, ev_ids) -> int:
    return db.execute(
        select(func.count())
        .select_from(TelemetryEvent)
        .where(
            TelemetryEvent.id.in_(ev_ids),
            TelemetryEvent.status == "failed",
            ~TelemetryEvent.id.in_(select(RoutingDecision.telemetry_event_id)),
        )
    ).scalar_one()


@router.get("/dashboard/timeseries")
def timeseries(
    limit: int = Query(200, ge=1, le=2000),
    source: Optional[str] = None,
    _: Principal = Depends(require("records:read")),
    db: Session = Depends(get_db),
):
    q = (
        select(TelemetryEvent, Prediction, RoutingDecision)
        .join(Prediction, Prediction.telemetry_event_id == TelemetryEvent.id)
        .join(RoutingDecision, RoutingDecision.telemetry_event_id == TelemetryEvent.id)
    )
    if source:
        q = q.where(TelemetryEvent.source == source)
    rows = db.execute(q.order_by(TelemetryEvent.id.desc()).limit(limit)).all()
    return {
        "items": [
            {
                "event_id": e.event_id,
                "device_id": e.device_id,
                "source": e.source,
                "received_at": e.received_at.isoformat(),
                "observed_at": e.observed_at.isoformat(),
                "last_rtt_ms": e.last_rtt_ms,
                "predicted_rtt_ms": p.predicted_rtt_ms,
                "method": p.method,
                "criticality": e.criticality,
                "destination": d.destination,
                "reason": d.reason,
            }
            for e, p, d in reversed(rows)
        ]
    }


@router.get("/system/info")
def system_info(request: Request, _: Principal = Depends(require("records:read"))):
    st = request.app.state
    return {
        "project": "AI-Based Multi-Cloud Migration Decision Framework for Healthcare Enterprises",
        "course": "BCSE355L Cloud Architecture Design, VIT Vellore (Team 11)",
        "team": [
            {"name": "Charles Jehanabad", "reg": "24BIT0522", "module": "datasets, LSTM prediction"},
            {"name": "Tanmay Kapoor", "reg": "24BIT0079", "module": "AHP decision engine"},
            {"name": "Rani Gupta", "reg": "24BIT0543", "module": "execution, backend, database, security, UI"},
        ],
        "api_version": request.app.version,
        "database": {"dialect": st.db.engine.dialect.name},
        "model": st.predictor.info(),
        "model_evaluation": _json(ROOT / "results" / "model" / "metrics.json"),
        "training_history": _json(st.settings.model_dir / "training_history.json"),
        "datasets": {
            "ripe_atlas_quality": _json(ROOT / "dataset" / "metadata" / "ripe_atlas_quality.json"),
            "ripe_atlas_splits": _json(ROOT / "dataset" / "metadata" / "ripe_atlas_splits.json"),
            "bidmc_quality": _json(ROOT / "dataset" / "metadata" / "bidmc_quality.json"),
        },
        "decision_engine": {
            "version": ENGINE_VERSION,
            "weight_set": WEIGHT_SET,
            "ahp": ahp_report(),
            "emergency_threshold": EMERGENCY_CRITICALITY_THRESHOLD,
            "latency_veto_ms": LATENCY_VETO_MS,
        },
        "execution": {
            "edge_adapter": st.executor.adapters["EDGE"].name,
            "cloud_adapter": st.executor.adapters["CLOUD"].name,
            "max_attempts": st.executor.max_attempts,
        },
        "alert_channels_configured": {c.name: c.configured() for c in st.alert_channels},
        "aws_services": _json(ROOT / "infra" / "aws" / "service_status.json"),
    }


@router.post("/demo/run")
def demo_run(body: DemoRun, request: Request, background: BackgroundTasks, p: Principal = Depends(require("demo:run"))):
    """Push N replayed (real RIPE Atlas + BIDMC) or simulated events through the real pipeline."""
    from data_ingestion.replay import build_replay_events
    from data_ingestion.simulator import build_simulated_events

    payloads = (
        build_replay_events(body.count, seed=body.seed)
        if body.mode == "replay"
        else build_simulated_events(body.count, scenario=body.scenario, seed=body.seed)
    )
    results = {"processed": 0, "duplicates": 0, "failed": 0, "by_destination": {}, "by_reason": {}}
    for pl in payloads:
        try:
            r, alert_ids = process_event(request.app.state.pipeline, EventIn(**pl), p)
        except PipelineError:
            results["failed"] += 1
            continue
        schedule_alerts(request, background, alert_ids)
        request.app.state.metrics.observe_event(r)
        results["duplicates" if r["duplicate"] else "processed"] += 1
        if r["decision"]:
            for k, v in (("by_destination", r["decision"]["destination"]), ("by_reason", r["decision"]["reason"])):
                results[k][v] = results[k].get(v, 0) + 1
    return results
