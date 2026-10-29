"""
src/execution/adapters.py  —  Owner: Rani Gupta (24BIT0543)
=============================================================
Execution adapters: where a routed reading is actually processed/stored.

Adapter name                 What really happens                          AWS target
---------------------------  -------------------------------------------  ---------------------
local-edge-simulator         appends the processed record to a local      AWS IoT Greengrass
                             edge buffer (runtime/edge_buffer/*.jsonl)    component
local-cloud-object-store     writes one JSON object per event under       Amazon S3 PutObject
                             runtime/cloud_objects/YYYY/MM/DD/ (S3 key
                             layout) - a LOCAL STAND-IN, not AWS
aws-s3                       boto3 put_object to S3_BUCKET                Amazon S3 (only when
                             (used only if CLOUD_ADAPTER=s3 and AWS       credentials are set up;
                             credentials are configured)                  status shown in /system)

Nothing in this module claims an AWS action happened unless the aws-s3 adapter was used
and S3 returned success.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


class ExecutionError(RuntimeError):
    pass


@dataclass
class AdapterOutput:
    adapter: str
    output_ref: str
    detail: dict


class ExecutionAdapter(Protocol):
    name: str
    destination: str

    def execute(self, payload: dict) -> AdapterOutput: ...


def _processed_record(payload: dict, where: str) -> dict:
    """The 'processing' both paths perform: summarise the reading for downstream consumers."""
    w = payload.get("network_window") or []
    rtts = [o.get("rtt_avg_ms") for o in w if o.get("rtt_avg_ms") is not None]
    return {
        "event_id": payload["event_id"],
        "device_id": payload["device_id"],
        "processed_at": where,
        "processed_ts": datetime.now(timezone.utc).isoformat(),
        "criticality": payload.get("criticality"),
        "vitals": payload.get("vitals"),
        "window_rtt_mean_ms": (sum(rtts) / len(rtts)) if rtts else None,
        "predicted_rtt_ms": payload.get("predicted_rtt_ms"),
        "decision_reason": payload.get("reason"),
    }


class LocalEdgeAdapter:
    name = "local-edge-simulator"
    destination = "EDGE"

    def __init__(self, runtime_dir: Path):
        self.dir = Path(runtime_dir) / "edge_buffer"
        self._lock = threading.Lock()

    def execute(self, payload: dict) -> AdapterOutput:
        if payload.get("simulate_failure") in ("edge", "both"):
            raise ExecutionError("injected edge failure (test/demo flag)")
        self.dir.mkdir(parents=True, exist_ok=True)
        rec = _processed_record(payload, "EDGE")
        f = self.dir / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        with self._lock, f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        return AdapterOutput(
            self.name,
            f"file://{f.name}#{payload['event_id']}",
            {"local_alert_raised": bool(payload.get("reason") == "override_critical_patient")},
        )


class LocalCloudObjectStoreAdapter:
    name = "local-cloud-object-store"
    destination = "CLOUD"

    def __init__(self, runtime_dir: Path):
        self.root = Path(runtime_dir) / "cloud_objects"

    def execute(self, payload: dict) -> AdapterOutput:
        if payload.get("simulate_failure") in ("cloud", "both"):
            raise ExecutionError("injected cloud failure (test/demo flag)")
        now = datetime.now(timezone.utc)
        key = f"{now:%Y/%m/%d}/{payload['device_id']}/{payload['event_id']}.json"
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(_processed_record(payload, "CLOUD")), encoding="utf-8")
        return AdapterOutput(self.name, f"local-s3://{key}", {})


class S3CloudAdapter:
    name = "aws-s3"
    destination = "CLOUD"

    def __init__(self, bucket: str):
        import boto3  # optional dependency, only needed when CLOUD_ADAPTER=s3

        self.bucket = bucket
        self.s3 = boto3.client("s3")

    def execute(self, payload: dict) -> AdapterOutput:
        if payload.get("simulate_failure") in ("cloud", "both"):
            raise ExecutionError("injected cloud failure (test/demo flag)")
        now = datetime.now(timezone.utc)
        key = f"processed/{now:%Y/%m/%d}/{payload['device_id']}/{payload['event_id']}.json"
        try:
            r = self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                ServerSideEncryption="AES256",
                Body=json.dumps(_processed_record(payload, "CLOUD")).encode(),
            )
        except Exception as exc:  # botocore errors
            raise ExecutionError(f"S3 put_object failed: {type(exc).__name__}") from exc
        return AdapterOutput(self.name, f"s3://{self.bucket}/{key}", {"etag": r.get("ETag")})


@dataclass
class ExecutionOutcome:
    requested_destination: str
    final_destination: str | None
    adapter: str
    status: str  # success | fallback_success | failed
    attempts: int
    attempt_log: list
    duration_ms: float
    output_ref: str | None
    error: str | None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Executor:
    """Runs the decided destination with retries; a failed CLOUD path falls back to EDGE.

    EDGE failures are never 'fixed' by sending data to the cloud: an emergency reading
    must stay local, so an EDGE failure is reported as failed (and the pipeline raises
    a CRITICAL execution_failure alert).
    """

    def __init__(self, edge: ExecutionAdapter, cloud: ExecutionAdapter, max_attempts: int = 3, backoff_s: float = 0.05):
        self.adapters = {"EDGE": edge, "CLOUD": cloud}
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s

    def _try(self, dest: str, payload: dict, log: list) -> AdapterOutput | None:
        adapter = self.adapters[dest]
        for attempt in range(1, self.max_attempts + 1):
            t0 = time.perf_counter()
            try:
                out = adapter.execute(payload)
                log.append(
                    {
                        "destination": dest,
                        "adapter": adapter.name,
                        "attempt": attempt,
                        "ok": True,
                        "ms": round((time.perf_counter() - t0) * 1000, 3),
                    }
                )
                return out
            except Exception as exc:
                log.append(
                    {
                        "destination": dest,
                        "adapter": adapter.name,
                        "attempt": attempt,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                        "ms": round((time.perf_counter() - t0) * 1000, 3),
                    }
                )
                if attempt < self.max_attempts:
                    time.sleep(self.backoff_s * attempt)
        return None

    def execute(self, destination: str, payload: dict) -> ExecutionOutcome:
        if destination not in self.adapters:
            raise ValueError(f"unknown destination {destination!r}")
        t0 = time.perf_counter()
        log: list = []
        out = self._try(destination, payload, log)
        status, final = ("success", destination) if out else ("failed", None)
        if out is None and destination == "CLOUD":
            out = self._try("EDGE", payload, log)
            if out:
                status, final = "fallback_success", "EDGE"
        return ExecutionOutcome(
            requested_destination=destination,
            final_destination=final,
            adapter=out.adapter if out else self.adapters[destination].name,
            status=status,
            attempts=len(log),
            attempt_log=log,
            duration_ms=round((time.perf_counter() - t0) * 1000, 3),
            output_ref=out.output_ref if out else None,
            error=None if status != "failed" else "; ".join(e.get("error", "") for e in log if not e["ok"])[:1000],
        )
