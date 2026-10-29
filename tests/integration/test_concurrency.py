"""Regression test for the lock-ordering deadlock found during the evidence run (see SECURITY_AND_TEST_REPORT.md):
concurrent ingestion + concurrent alert dispatch on one SQLite file must neither deadlock nor fork the audit chain."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from backend.app import create_app
from backend.audit import verify_chain
from backend.schemas import EventIn
from backend.security import Principal
from backend.services.pipeline import process_event
from tests.conftest import FakeChannel, event, make_settings


class SlowChannel(FakeChannel):
    def send(self, alert):
        time.sleep(0.05)  # network latency while other requests are writing
        return super().send(alert)


def test_parallel_ingest_and_alert_dispatch(tmp_path):
    ch = SlowChannel("slow")
    app = create_app(make_settings(tmp_path, alerts_sync=False), alert_channels=[ch])
    p = Principal(user_id=None, username="concurrency-test", role="device")
    payloads = [EventIn(**event(f"conc-{i:03d}", criticality=9.5 if i % 3 == 0 else 2.0)) for i in range(45)]

    def one(pl):
        res, alert_ids = process_event(app.state.pipeline, pl, p)
        for aid in alert_ids:  # dispatch in the same worker pool, interleaved with other ingests
            app.state.dispatch_alert(aid)
        return res["status"]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(8) as pool:
        statuses = list(pool.map(one, payloads))
    assert time.perf_counter() - t0 < 60
    assert statuses.count("completed") == 45
    assert len(ch.sent) == 15
    with app.state.db.session() as db:
        v = verify_chain(db)
    assert v["valid"], v
