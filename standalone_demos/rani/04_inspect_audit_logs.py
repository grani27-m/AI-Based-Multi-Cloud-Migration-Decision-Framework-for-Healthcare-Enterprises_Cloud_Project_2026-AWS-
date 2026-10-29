"""
04 - Inspect the persistent database DIRECTLY (no API): table counts, recent audit entries, hash-chain verification,
     execution history, alerts and every delivery attempt.

    python 04_inspect_audit_logs.py
    python 04_inspect_audit_logs.py --limit 30
    python 04_inspect_audit_logs.py --tamper-demo     # edits ONE audit row in a COPY of the DB and shows detection

Works while the backend is running or stopped. Never modifies runtime/app.db.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from demo_common import ROOT, load_env


def _db():
    from backend.config import Settings
    from backend.db import Database

    return Database(Settings.from_env().database_url)


def tamper_demo(url: str) -> int:
    from sqlalchemy import select

    from backend.audit import verify_chain
    from backend.db import Database
    from backend.models import AuditLog

    if not url.startswith("sqlite:///"):
        print("--tamper-demo works on the SQLite file only")
        return 2
    src = Path(url.removeprefix("sqlite:///"))
    src = src if src.is_absolute() else ROOT / src
    copy = src.with_name("tamper_demo_copy.db")
    import sqlite3

    with sqlite3.connect(src) as a, sqlite3.connect(copy) as b:  # backup API also copies pages still in the WAL file
        a.backup(b)
    db = Database(f"sqlite:///{copy}")
    with db.session() as s:
        before = verify_chain(s)
        rows = s.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
        if len(rows) < 3:
            print("need at least 3 audit entries - run 03 first")
            return 2
        target = rows[len(rows) // 2]
        print(f"copy: {copy}\nbefore tampering: {before}")
        print(f"editing audit row id={target.id} action={target.action}: actor '{target.actor}' -> 'attacker'")
        target.actor = "attacker"
    with db.session() as s:
        after = verify_chain(s)
    print(f"after tampering:  {after}")
    db.dispose()
    for f in (copy, copy.with_name(copy.name + "-wal"), copy.with_name(copy.name + "-shm")):
        f.unlink(missing_ok=True)
    ok = before["valid"] and not after["valid"] and after["first_broken_id"] == target.id
    print("\nTamper detected at the edited row." if ok else "\nUNEXPECTED: tampering not detected")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--tamper-demo", action="store_true")
    a = ap.parse_args()
    load_env()
    from sqlalchemy import func, select

    from backend.audit import verify_chain
    from backend.models import Alert, AlertDelivery, AuditLog, Base, ExecutionRecord, TelemetryEvent

    db = _db()
    if a.tamper_demo:
        return tamper_demo(db.url)
    print(f"database: {db.url}\n")
    with db.session() as s:
        print("table rows:")
        for name, t in sorted(Base.metadata.tables.items()):
            print(f"  {name:<20} {s.execute(select(func.count()).select_from(t)).scalar_one():>7}")

        print(f"\nlast {a.limit} audit entries (append-only, hash-chained):")
        for r in reversed(s.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(a.limit)).scalars().all()):
            print(f"  #{r.id:<5} {r.ts[:19]} {r.actor:<22} {r.action:<24} {r.resource:<34} {r.hash[:12]}… prev {r.prev_hash[:12]}…")
        v = verify_chain(s)
        print(f"\nhash chain: {'VALID' if v['valid'] else 'BROKEN'} - {v['checked']} entries checked"
              + (f", head {v['head_hash'][:16]}…" if v["valid"] else f", first broken id {v['first_broken_id']}: {v['problem']}"))

        print(f"\nexecution history (last {a.limit}):")
        q = (select(ExecutionRecord, TelemetryEvent.event_id).join(TelemetryEvent, TelemetryEvent.id == ExecutionRecord.telemetry_event_id)
             .order_by(ExecutionRecord.id.desc()).limit(a.limit))
        for ex, eid in reversed(s.execute(q).all()):
            print(f"  #{ex.id:<5} {eid[:34]:<34} {ex.requested_destination:>5} -> {str(ex.final_destination):<5} {ex.status:<17} "
                  f"adapter={ex.adapter:<22} attempts={ex.attempts} {ex.duration_ms:.1f} ms")

        print(f"\nalerts and delivery attempts (last {a.limit}):")
        for al in reversed(s.execute(select(Alert).order_by(Alert.id.desc()).limit(a.limit)).scalars().all()):
            print(f"  alert #{al.id} {al.severity:<8} {al.kind:<20} status={al.status}")
            for d in s.execute(select(AlertDelivery).where(AlertDelivery.alert_id == al.id).order_by(AlertDelivery.id)).scalars():
                print(f"      -> {d.channel:<10} attempt {d.attempt} {d.status:<10} {str(d.detail)[:90]}")
    db.dispose()
    return 0 if v["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
