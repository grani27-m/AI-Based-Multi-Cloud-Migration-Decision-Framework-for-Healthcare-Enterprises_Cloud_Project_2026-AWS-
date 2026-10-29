"""
backend/audit.py  —  Owner: Rani Gupta
=======================================
Append-only, SHA-256 hash-chained audit trail.

    hash_i = SHA256( canonical_json({prev, ts, actor, action, resource, detail}) )
    prev_i = hash_(i-1)   (GENESIS = 64 zeros for the first row)

verify_chain() recomputes every link, so an edited, deleted, inserted or reordered
row is detected and the first broken row id is reported.

Limitations (also in team_work/rani/SECURITY_NOTES.md): the chain is TAMPER-EVIDENT,
not tamper-proof. Someone with database write access could rewrite the whole chain;
protection requires exporting checkpoints (latest hash) to a separately controlled
store such as S3 Object Lock or CloudWatch Logs. /api/v1/audit/verify returns the
head hash so it can be checkpointed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.models import AuditLog

GENESIS = "0" * 64
# Concurrency: on PostgreSQL a transaction-scoped advisory lock serialises chain appends; on SQLite every
# transaction starts with BEGIN IMMEDIATE (backend/db.py). No Python-level lock is used on purpose: mixing one
# with database locks caused a lock-ordering deadlock (found in the evidence run, see reports/SECURITY_AND_TEST_REPORT.md).


def digest(prev: str, ts: str, actor: str, action: str, resource: str, detail: dict) -> str:
    body = json.dumps(
        {"prev": prev, "ts": ts, "actor": actor, "action": action, "resource": resource, "detail": detail},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def write_audit(db: Session, actor: str, action: str, resource: str, detail: dict | None = None) -> AuditLog:
    """Append one entry in the caller's transaction. NEVER put patient data or secrets in detail."""
    detail = json.loads(json.dumps(detail or {}, default=str))
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(724001)"))
    last = db.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    prev = last or GENESIS
    ts = datetime.now(timezone.utc).isoformat()
    row = AuditLog(
        ts=ts,
        actor=actor,
        action=action,
        resource=resource,
        detail=detail,
        prev_hash=prev,
        hash=digest(prev, ts, actor, action, resource, detail),
    )
    db.add(row)
    db.flush()
    return row


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    n = 0
    for row in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars():
        n += 1
        expected = digest(prev, row.ts, row.actor, row.action, row.resource, row.detail)
        if row.prev_hash != prev or row.hash != expected:
            return {
                "valid": False,
                "checked": n,
                "first_broken_id": row.id,
                "problem": "prev_hash mismatch (row deleted/reordered/inserted)"
                if row.prev_hash != prev
                else "content hash mismatch (row edited)",
                "head_hash": None,
            }
        prev = row.hash
    return {"valid": True, "checked": n, "first_broken_id": None, "problem": None, "head_hash": prev}
