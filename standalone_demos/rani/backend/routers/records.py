"""Devices, executions, alerts and audit endpoints.  Owner: Rani Gupta"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.audit import verify_chain, write_audit
from backend.deps import get_db, require
from backend.models import Alert, AuditLog, Device, ExecutionRecord, TelemetryEvent
from backend.security import Principal

router = APIRouter(prefix="/api/v1", tags=["records"])


@router.get("/devices")
def devices(_: Principal = Depends(require("records:read")), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(TelemetryEvent.device_id, func.count()).group_by(TelemetryEvent.device_id)).all())
    out = []
    for d in db.execute(select(Device).order_by(Device.last_seen_at.desc())).scalars():
        last = db.execute(
            select(TelemetryEvent).where(TelemetryEvent.device_id == d.id).order_by(TelemetryEvent.id.desc()).limit(1)
        ).scalar_one_or_none()
        out.append(
            {
                "id": d.id,
                "kind": d.kind,
                "is_active": d.is_active,
                "first_seen_at": d.first_seen_at.isoformat(),
                "last_seen_at": d.last_seen_at.isoformat(),
                "events": counts.get(d.id, 0),
                "last_event": None
                if last is None
                else {
                    "event_id": last.event_id,
                    "source": last.source,
                    "criticality": last.criticality,
                    "last_rtt_ms": last.last_rtt_ms,
                    "predicted_rtt_ms": last.prediction.predicted_rtt_ms if last.prediction else None,
                    "destination": last.decision.destination if last.decision else None,
                    "reason": last.decision.reason if last.decision else None,
                },
            }
        )
    return {"devices": out}


@router.get("/executions")
def executions(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(require("records:read")),
    db: Session = Depends(get_db),
):
    q = select(ExecutionRecord, TelemetryEvent.event_id, TelemetryEvent.device_id).join(
        TelemetryEvent, TelemetryEvent.id == ExecutionRecord.telemetry_event_id
    )
    if status:
        q = q.where(ExecutionRecord.status == status)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(ExecutionRecord.id.desc()).limit(limit).offset(offset)).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "event_id": eid,
                "device_id": dev,
                "requested_destination": r.requested_destination,
                "final_destination": r.final_destination,
                "adapter": r.adapter,
                "status": r.status,
                "attempts": r.attempts,
                "duration_ms": r.duration_ms,
                "output_ref": r.output_ref,
                "error": r.error,
                "created_at": r.created_at.isoformat(),
            }
            for r, eid, dev in rows
        ],
    }


@router.get("/alerts")
def alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(require("records:read")),
    db: Session = Depends(get_db),
):
    q = select(Alert)
    if status:
        q = q.where(Alert.status == status)
    if severity:
        q = q.where(Alert.severity == severity)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(Alert.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": a.id,
                "event_id": a.event.event_id,
                "device_id": a.device_id,
                "severity": a.severity,
                "kind": a.kind,
                "message": a.message,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
                "delivered_at": a.delivered_at.isoformat() if a.delivered_at else None,
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "deliveries": [
                    {
                        "channel": d.channel,
                        "attempt": d.attempt,
                        "status": d.status,
                        "detail": d.detail,
                        "latency_ms": round(d.latency_ms, 1),
                        "attempted_at": d.attempted_at.isoformat(),
                    }
                    for d in a.deliveries
                ],
            }
            for a in rows
        ],
    }


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, p: Principal = Depends(require("alerts:ack")), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "alert not found")
    if a.acknowledged_at is None:
        a.acknowledged_by, a.acknowledged_at = p.user_id, datetime.now(timezone.utc)
        write_audit(db, p.username, "alert_acknowledged", f"alert/{a.id}", {})
    return {"id": a.id, "acknowledged_at": a.acknowledged_at.isoformat()}


@router.get("/audit")
def audit(
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(require("audit:read")),
    db: Session = Depends(get_db),
):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "ts": r.ts,
                "actor": r.actor,
                "action": r.action,
                "resource": r.resource,
                "detail": r.detail,
                "prev_hash": r.prev_hash,
                "hash": r.hash,
            }
            for r in rows
        ],
    }


@router.get("/audit/verify")
def audit_verify(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    res = verify_chain(db)
    res["verified_at"] = datetime.now(timezone.utc).isoformat()
    res["verified_by"] = p.username
    return res
