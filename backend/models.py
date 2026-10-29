"""
backend/models.py  —  Owner: Rani Gupta
========================================
ORM schema (ER diagram: integration/DATABASE_SCHEMA.md). One telemetry event flows:

  telemetry_events 1-1 predictions 1-1 routing_decisions 1-n execution_records
        |                                   (attempt history is inside one record)
        +-- 0-n alerts 1-n alert_deliveries
  audit_log is append-only and hash-chained; it references rows by resource string.

All timestamps are timezone-aware UTC. No patient identifiers are stored: devices
are identified by a device ID and vitals are stored only as three numbers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


TS = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    __table_args__ = (CheckConstraint("role IN ('admin','doctor','auditor','device')", name="ck_users_role"),)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="unknown")
    first_seen_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # idempotency key
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    source: Mapped[str] = mapped_column(String(16), index=True)  # simulated | replay | live | test
    observed_at: Mapped[datetime] = mapped_column(TS, index=True)
    received_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    criticality: Mapped[float] = mapped_column(Float)
    criticality_method: Mapped[str] = mapped_column(String(96))
    vitals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    cloud_cost_index: Mapped[float] = mapped_column(Float)
    network_window: Mapped[list] = mapped_column(JSON)
    last_rtt_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="received", index=True)  # received|completed|failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    prediction: Mapped[Optional["Prediction"]] = relationship(back_populates="event", uselist=False)
    decision: Mapped[Optional["RoutingDecision"]] = relationship(back_populates="event", uselist=False)
    executions: Mapped[list["ExecutionRecord"]] = relationship(back_populates="event")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="event")
    __table_args__ = (
        CheckConstraint("criticality >= 0 AND criticality <= 10", name="ck_events_criticality"),
        CheckConstraint("cloud_cost_index >= 0 AND cloud_cost_index <= 1", name="ck_events_cost"),
        CheckConstraint("source IN ('simulated','replay','live','test')", name="ck_events_source"),
    )


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telemetry_event_id: Mapped[int] = mapped_column(ForeignKey("telemetry_events.id", ondelete="CASCADE"),
                                                    unique=True)
    predicted_rtt_ms: Mapped[float] = mapped_column(Float)
    risk: Mapped[str] = mapped_column(String(8))
    method: Mapped[str] = mapped_column(String(32), index=True)  # lstm | persistence_fallback
    model_version: Mapped[str] = mapped_column(String(48))
    horizon_s: Mapped[int] = mapped_column(Integer)
    inference_ms: Mapped[float] = mapped_column(Float)
    last_observed_rtt_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    event: Mapped[TelemetryEvent] = relationship(back_populates="prediction")


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telemetry_event_id: Mapped[int] = mapped_column(ForeignKey("telemetry_events.id", ondelete="CASCADE"),
                                                    unique=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("predictions.id"), nullable=True)
    destination: Mapped[str] = mapped_column(String(8), index=True)
    reason: Mapped[str] = mapped_column(String(48), index=True)
    veto: Mapped[str] = mapped_column(String(24))
    edge_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cloud_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight_set: Mapped[str] = mapped_column(String(32))
    weights: Mapped[dict] = mapped_column(JSON)
    normalised: Mapped[dict] = mapped_column(JSON, default=dict)
    contributions: Mapped[dict] = mapped_column(JSON, default=dict)
    engine_version: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    event: Mapped[TelemetryEvent] = relationship(back_populates="decision")
    __table_args__ = (CheckConstraint("destination IN ('EDGE','CLOUD')", name="ck_decisions_destination"),)


class ExecutionRecord(Base):
    __tablename__ = "execution_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telemetry_event_id: Mapped[int] = mapped_column(ForeignKey("telemetry_events.id", ondelete="CASCADE"),
                                                    index=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("routing_decisions.id", ondelete="CASCADE"), index=True)
    requested_destination: Mapped[str] = mapped_column(String(8))
    final_destination: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    adapter: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24), index=True)  # success | fallback_success | failed
    attempts: Mapped[int] = mapped_column(Integer)
    attempt_log: Mapped[list] = mapped_column(JSON, default=list)
    duration_ms: Mapped[float] = mapped_column(Float)
    output_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    event: Mapped[TelemetryEvent] = relationship(back_populates="executions")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telemetry_event_id: Mapped[int] = mapped_column(ForeignKey("telemetry_events.id", ondelete="CASCADE"),
                                                    index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(10), index=True)  # CRITICAL | WARNING
    kind: Mapped[str] = mapped_column(String(32))  # emergency_override | network_veto | execution_failure
    message: Mapped[str] = mapped_column(Text)
    # triggered -> (delivered | partially_delivered | failed | not_configured | not_notified)
    status: Mapped[str] = mapped_column(String(24), default="triggered", index=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    acknowledged_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    event: Mapped[TelemetryEvent] = relationship(back_populates="alerts")
    deliveries: Mapped[list["AlertDelivery"]] = relationship(back_populates="alert", order_by="AlertDelivery.id")
    __table_args__ = (UniqueConstraint("telemetry_event_id", "kind", name="uq_alert_event_kind"),)


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(16))  # telegram | email | webhook
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12))   # sent | failed | skipped
    detail: Mapped[str] = mapped_column(Text, default="")  # sanitised: never contains credentials
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    attempted_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    alert: Mapped[Alert] = relationship(back_populates="deliveries")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(48), index=True)
    resource: Mapped[str] = mapped_column(String(128))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


Index("ix_events_source_status", TelemetryEvent.source, TelemetryEvent.status)
