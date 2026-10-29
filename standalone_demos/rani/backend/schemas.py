"""
backend/schemas.py  —  Owner: Rani Gupta (contract agreed with Charles and Tanmay)
===================================================================================
Pydantic request/response models = the single shared event contract
(documented in integration/API_CONTRACT.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.prediction.features import WINDOW

ID_PATTERN = r"^[A-Za-z0-9_.:\-]{3,64}$"
Source = Literal["simulated", "replay", "live", "test"]


class NetworkObservation(BaseModel):
    """One network measurement round (same schema as a RIPE Atlas ping result after parsing)."""

    model_config = ConfigDict(extra="forbid")
    timestamp: datetime
    rtt_avg_ms: Optional[float] = Field(None, ge=0, le=5000)
    rtt_min_ms: Optional[float] = Field(None, ge=0, le=5000)
    rtt_max_ms: Optional[float] = Field(None, ge=0, le=5000)
    jitter_ms: Optional[float] = Field(None, ge=0, le=5000)
    loss_pct: float = Field(..., ge=0, le=100)

    @model_validator(mode="after")
    def _rtts(self):
        if self.loss_pct < 100 and None in (self.rtt_avg_ms, self.rtt_min_ms, self.rtt_max_ms):
            raise ValueError("rtt_avg/min/max are required unless loss_pct == 100")
        if self.rtt_avg_ms is not None and self.rtt_min_ms is not None and self.rtt_max_ms is not None:
            if not self.rtt_min_ms <= self.rtt_avg_ms <= self.rtt_max_ms:
                raise ValueError("require rtt_min_ms <= rtt_avg_ms <= rtt_max_ms")
        return self


class Vitals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hr: float = Field(..., ge=10, le=300, description="heart/pulse rate, beats per minute")
    resp: float = Field(..., ge=0, le=80, description="respiration rate, breaths per minute")
    spo2: float = Field(..., ge=30, le=100, description="oxygen saturation, %")


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: Optional[str] = Field(
        None, pattern=ID_PATTERN, description="client idempotency key; server generates one if absent"
    )
    device_id: str = Field(..., pattern=ID_PATTERN)
    device_kind: str = Field("unknown", max_length=32)
    source: Source
    observed_at: Optional[datetime] = None
    network_window: list[NetworkObservation] = Field(..., min_length=WINDOW, max_length=WINDOW)
    vitals: Optional[Vitals] = None
    criticality: Optional[float] = Field(None, ge=0, le=10)
    cloud_cost_index: float = Field(..., ge=0, le=1)
    provenance: dict = Field(default_factory=dict)
    simulate_failure: Optional[Literal["edge", "cloud", "both"]] = None

    @model_validator(mode="after")
    def _rules(self):
        if (self.vitals is None) == (self.criticality is None):
            raise ValueError("provide exactly one of 'vitals' (criticality is derived) or 'criticality'")
        if self.simulate_failure and self.source not in ("test", "simulated"):
            raise ValueError("simulate_failure is only allowed for source 'test' or 'simulated'")
        ts = [o.timestamp for o in self.network_window]
        if any(b <= a for a, b in zip(ts, ts[1:])):
            raise ValueError("network_window timestamps must be strictly increasing")
        return self

    @field_validator("provenance")
    @classmethod
    def _small(cls, v: dict):
        if len(str(v)) > 2000:
            raise ValueError("provenance too large")
        return v


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(..., pattern=r"^[a-z0-9_.\-]{3,64}$")
    full_name: str = Field("", max_length=128)
    password: str = Field(..., min_length=10, max_length=256)
    role: Literal["admin", "doctor", "auditor", "device"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]


class DemoRun(BaseModel):
    mode: Literal["replay", "simulate"] = "replay"
    count: int = Field(20, ge=1, le=500)
    scenario: Literal["mixed", "normal", "degraded", "emergency", "failure"] = "mixed"
    seed: int = 7
