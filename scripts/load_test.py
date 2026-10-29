"""
Reproducible load test of POST /api/v1/events against a running API (stdlib threads + httpx).

    python -m scripts.load_test --users 10 --requests 50 --out results/load/load_test_10u.json

Reports request count, errors, throughput and p50/p95/p99 latency. Uses simulated events
(source=simulated, unique event IDs per run) so it never pollutes replay statistics.
Objective 3 of the report: p95 of POST /ingest below 200 ms.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from data_ingestion.simulator import build_simulated_events


def pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    f, c = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("API_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--requests", type=int, default=50, help="requests per user")
    ap.add_argument("--user", default="sim-device")
    ap.add_argument("--password-env", default="DEVICE_PASSWORD")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    tok = httpx.post(
        f"{a.api}/api/v1/auth/login", json={"username": a.user, "password": os.environ[a.password_env]}
    ).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    run = uuid.uuid4().hex[:6]
    events = build_simulated_events(a.users * a.requests, scenario="mixed", seed=int(time.time()))
    for i, e in enumerate(events):
        e["event_id"] = f"load-{run}-{i:06d}"
        e.pop("simulate_failure", None)

    def worker(chunk):
        out = []
        with httpx.Client(base_url=a.api, timeout=60, headers=h) as c:
            for e in chunk:
                t0 = time.perf_counter()
                try:
                    code = c.post("/api/v1/events", json=e).status_code
                except Exception:
                    code = 0
                out.append((code, (time.perf_counter() - t0) * 1000))
        return out

    chunks = [events[i :: a.users] for i in range(a.users)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(a.users) as pool:
        res = [r for part in pool.map(worker, chunks) for r in part]
    wall = time.perf_counter() - t0
    lat = [ms for code, ms in res if code in (200, 201)]
    errors = sum(1 for code, _ in res if code not in (200, 201))
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    summary = {
        "api": a.api,
        "concurrent_users": a.users,
        "requests": len(res),
        "errors": errors,
        "duration_s": round(wall, 2),
        "throughput_rps": round(len(res) / wall, 2),
        "latency_ms": {
            "mean": round(statistics.mean(lat), 1),
            "p50": round(pct(lat, 50), 1),
            "p95": round(pct(lat, 95), 1),
            "p99": round(pct(lat, 99), 1),
            "max": round(max(lat), 1),
        },
        "objective_3_p95_below_200ms": pct(lat, 95) < 200,
        "commit": commit,
        "environment": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "cpus": os.cpu_count(),
            "note": "client and server on the same host",
        },
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(json.dumps(summary, indent=2))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
