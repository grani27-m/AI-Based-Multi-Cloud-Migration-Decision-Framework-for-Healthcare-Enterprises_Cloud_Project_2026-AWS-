"""Telemetry ingestion and event history.  Owner: Rani Gupta"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.deps import get_db, require
from backend.models import RoutingDecision, TelemetryEvent
from backend.schemas import EventIn
from backend.security import Principal
from backend.services.pipeline import PipelineError, event_result, process_event

router = APIRouter(prefix="/api/v1", tags=["events"])


def schedule_alerts(request: Request, background: BackgroundTasks | None, alert_ids: list[int]) -> None:
    app = request.app
    for aid in alert_ids:
        if app.state.settings.alerts_sync or background is None:
            app.state.dispatch_alert(aid)
        else:
            background.add_task(app.state.dispatch_alert, aid)


@router.post("/events", status_code=201)
def ingest(body: EventIn, request: Request, background: BackgroundTasks,
           p: Principal = Depends(require("events:create"))):
    request.app.state.rate_limiter.check(p.user_id)
    try:
        result, alert_ids = process_event(request.app.state.pipeline, body, p)
    except PipelineError as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.message, "event_id": e.event_id})
    schedule_alerts(request, background, alert_ids)
    request.app.state.metrics.observe_event(result)
    return JSONResponse(status_code=200 if result["duplicate"] else 201, content=result)


@router.get("/events")
def list_events(source: Optional[str] = None, device_id: Optional[str] = None, status: Optional[str] = None,
                destination: Optional[str] = None, reason: Optional[str] = None,
                limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                _: Principal = Depends(require("records:read")), db: Session = Depends(get_db)):
    q = select(TelemetryEvent)
    if destination or reason:
        q = q.join(RoutingDecision, RoutingDecision.telemetry_event_id == TelemetryEvent.id)
        if destination:
            q = q.where(RoutingDecision.destination == destination)
        if reason:
            q = q.where(RoutingDecision.reason == reason)
    for col, val in ((TelemetryEvent.source, source), (TelemetryEvent.device_id, device_id),
                     (TelemetryEvent.status, status)):
        if val:
            q = q.where(col == val)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(TelemetryEvent.id.desc()).limit(limit).offset(offset)).scalars().all()
    items = []
    for ev in rows:
        d, pr = ev.decision, ev.prediction
        items.append({"event_id": ev.event_id, "device_id": ev.device_id, "source": ev.source, "status": ev.status,
                      "observed_at": ev.observed_at.isoformat(), "received_at": ev.received_at.isoformat(),
                      "criticality": ev.criticality, "criticality_method": ev.criticality_method,
                      "cloud_cost_index": ev.cloud_cost_index, "last_rtt_ms": ev.last_rtt_ms,
                      "predicted_rtt_ms": pr.predicted_rtt_ms if pr else None,
                      "prediction_method": pr.method if pr else None, "risk": pr.risk if pr else None,
                      "destination": d.destination if d else None, "reason": d.reason if d else None,
                      "edge_score": d.edge_score if d else None, "cloud_score": d.cloud_score if d else None})
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/events/{event_id}")
def get_event(event_id: str, _: Principal = Depends(require("records:read")), db: Session = Depends(get_db)):
    ev = db.execute(select(TelemetryEvent).where(TelemetryEvent.event_id == event_id)).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "event not found")
    r = event_result(db, ev)
    r["network_window"] = ev.network_window
    r["provenance"] = ev.provenance
    return r
