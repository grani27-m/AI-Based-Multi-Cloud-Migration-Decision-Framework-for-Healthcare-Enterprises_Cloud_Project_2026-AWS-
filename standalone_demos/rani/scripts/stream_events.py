"""
Stream events to a RUNNING API over HTTP, exactly like a device gateway would.

    python -m scripts.stream_events --mode replay   --count 200 --rate 5 --user sim-device --password-env DEVICE_PASSWORD
    python -m scripts.stream_events --mode simulate --scenario degraded --count 30

replay   = real RIPE Atlas (held-out test period) + real PhysioNet BIDMC vitals
simulate = labelled synthetic scenarios (data_ingestion/simulator.py)
"""

from __future__ import annotations

import argparse
import getpass
import os
import time

import httpx

from data_ingestion.replay import build_replay_events
from data_ingestion.simulator import build_simulated_events


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("API_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--mode", choices=["replay", "simulate"], default="replay")
    ap.add_argument("--scenario", default="mixed")
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--rate", type=float, default=2.0, help="events per second")
    ap.add_argument("--seed", type=int, default=int(time.time()) % 100000)
    ap.add_argument("--user", default=os.environ.get("STREAM_USER", "sim-device"))
    ap.add_argument("--password-env", default="DEVICE_PASSWORD")
    a = ap.parse_args(argv)
    pw = os.environ.get(a.password_env) or getpass.getpass(f"password for {a.user}: ")
    with httpx.Client(base_url=a.api, timeout=30) as c:
        tok = c.post("/api/v1/auth/login", json={"username": a.user, "password": pw})
        tok.raise_for_status()
        h = {"Authorization": f"Bearer {tok.json()['access_token']}"}
        evs = (
            build_replay_events(a.count, seed=a.seed)
            if a.mode == "replay"
            else build_simulated_events(a.count, scenario=a.scenario, seed=a.seed)
        )
        for i, e in enumerate(evs, 1):
            r = c.post("/api/v1/events", json=e, headers=h)
            if r.status_code in (200, 201):
                b = r.json()
                d = b.get("decision") or {}
                print(
                    f"[{i:4d}] {b['device_id']:<16} crit={b['criticality']['score']:>5.2f} "
                    f"rtt->{(b.get('prediction') or {}).get('predicted_rtt_ms', 0):>7.1f}ms "
                    f"{d.get('destination', '-'):<5} {d.get('reason', '-'):<28} exec={(b.get('execution') or {}).get('status')}"
                    f"{' (duplicate)' if b['duplicate'] else ''}"
                )
            else:
                print(f"[{i:4d}] HTTP {r.status_code}: {r.text[:200]}")
            time.sleep(1.0 / a.rate if a.rate > 0 else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
