"""
06 - Prove that data survives a backend restart.

    python 06_persistence_check.py              # uses runtime/app.db (stop 02_start_backend.py first, or use --port)
    python 06_persistence_check.py --port 8011

Starts the backend as a child process, stores 3 new events, STOPS the process, starts a NEW process on the same
database file, and checks the events, their decisions/executions and the audit chain are all still there.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from demo_common import ROOT, load_env, login, require_env, server_running, wait_ready


def start(port: int) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(ROOT / "02_start_backend.py"), "--port", str(port)], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop(p: subprocess.Popen) -> None:
    p.terminate()
    try:
        p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8011)
    a = ap.parse_args()
    env = load_env()
    require_env("DEVICE_PASSWORD", "BOOTSTRAP_ADMIN_PASSWORD")
    import httpx

    from data_ingestion.replay import build_replay_events

    base = f"http://127.0.0.1:{a.port}"
    if server_running(base):
        print(f"something is already listening on port {a.port}; choose another --port")
        return 2
    seed = int(time.time()) % 1_000_000
    events = build_replay_events(3, seed=seed)
    print(f"[1] starting backend on {base}")
    p = start(a.port)
    try:
        if not wait_ready(base):
            print("backend did not become ready")
            return 1
        with httpx.Client(base_url=base, timeout=60) as c:
            dev = login(c, env.get("STREAM_USER") or "sim-device", env["DEVICE_PASSWORD"])
            adm = login(c, env.get("BOOTSTRAP_ADMIN_USERNAME") or "admin", env["BOOTSTRAP_ADMIN_PASSWORD"])
            before = {}
            for e in events:
                b = c.post("/api/v1/events", json=e, headers=dev).raise_for_status().json()
                before[b["event_id"]] = (b["decision"]["destination"], b["execution"]["status"])
                print(f"    stored {b['event_id']} -> {before[b['event_id']]}")
            total_before = c.get("/api/v1/events?limit=1", headers=adm).json()["total"]
            audit_before = c.get("/api/v1/audit/verify", headers=adm).json()
    finally:
        print(f"[2] stopping backend pid {p.pid}")
        stop(p)
    time.sleep(1)
    print(f"[3] backend stopped: reachable={server_running(base)}")
    print("[4] starting a NEW backend process on the same database")
    p2 = start(a.port)
    checks = []
    try:
        if not wait_ready(base):
            print("backend did not become ready after restart")
            return 1
        with httpx.Client(base_url=base, timeout=60) as c:
            adm = login(c, env.get("BOOTSTRAP_ADMIN_USERNAME") or "admin", env["BOOTSTRAP_ADMIN_PASSWORD"])
            for eid, (dest, st) in before.items():
                r = c.get(f"/api/v1/events/{eid}", headers=adm)
                ok = r.status_code == 200 and (r.json()["decision"]["destination"], r.json()["execution"]["status"]) == (dest, st)
                checks.append((f"event {eid} still stored with same decision/execution", ok))
            total_after = c.get("/api/v1/events?limit=1", headers=adm).json()["total"]
            checks.append((f"event count unchanged across restart ({total_before} -> {total_after})", total_before == total_after))
            v = c.get("/api/v1/audit/verify", headers=adm).json()
            checks.append((f"audit chain valid after restart ({v['checked']} entries, was {audit_before['checked']})",
                           v["valid"] and v["checked"] >= audit_before["checked"]))
            checks.append(("login works after restart (users persisted)", True))
    finally:
        stop(p2)
    print("\nchecks:")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    bad = sum(not ok for _, ok in checks)
    print(f"\n{len(checks) - bad}/{len(checks)} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
