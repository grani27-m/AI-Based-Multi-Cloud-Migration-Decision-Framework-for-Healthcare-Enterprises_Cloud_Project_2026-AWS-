"""
03 - Drive the RUNNING backend over HTTP: real replay events, labelled simulated scenarios, failure handling,
     idempotency, invalid input and authorisation checks.   (start 02_start_backend.py first)

    python 03_run_execution_demo.py
    python 03_run_execution_demo.py --replay 40

Every request goes through the real pipeline: validate -> LSTM forecast -> AHP + safety vetoes -> execution adapter
(LOCAL stand-ins for edge node and cloud, labelled 'local-edge' / 'local-cloud') -> database -> alerts -> audit log.
"""

from __future__ import annotations

import argparse
import copy
import time

from demo_common import api_url, load_env, login, require_env, server_running


def row(i, label, b):
    d, ex, p = b.get("decision") or {}, b.get("execution") or {}, b.get("prediction") or {}
    print(f"{i:>3} {label:<22} {b['device_id']:<15} crit={b['criticality']['score']:>5.2f} "
          f"pred={p.get('predicted_rtt_ms') or float('nan'):>7.1f}ms {d.get('destination', '-'):<5} "
          f"{d.get('reason', '-'):<32} exec={ex.get('status')}/{ex.get('final_destination')} "
          f"attempts={ex.get('attempts')} alerts={len(b.get('alerts') or [])}{' DUPLICATE' if b['duplicate'] else ''}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", type=int, default=20, help="number of real replay events")
    ap.add_argument("--seed", type=int, default=int(time.time()) % 100000)
    a = ap.parse_args()
    env = load_env()
    require_env("DEVICE_PASSWORD", "BOOTSTRAP_ADMIN_PASSWORD")
    import httpx

    from data_ingestion.replay import build_replay_events
    from data_ingestion.simulator import build_simulated_events

    base = api_url()
    if not server_running(base):
        print(f"backend not reachable at {base} - start it first: python 02_start_backend.py")
        return 2
    checks: list[tuple[str, bool, str]] = []
    with httpx.Client(base_url=base, timeout=60) as c:
        dev = login(c, env.get("STREAM_USER") or "sim-device", env["DEVICE_PASSWORD"])
        adm = login(c, env.get("BOOTSTRAP_ADMIN_USERNAME") or "admin", env["BOOTSTRAP_ADMIN_PASSWORD"])
        print(f"API {base}  (device and admin logged in)\n")

        print(f"--- {a.replay} REAL replay events (RIPE Atlas test-period windows + PhysioNet BIDMC vitals) ---")
        for i, e in enumerate(build_replay_events(a.replay, seed=a.seed), 1):
            r = c.post("/api/v1/events", json=e, headers=dev)
            r.raise_for_status()
            row(i, "replay (real data)", r.json())

        print("\n--- labelled SIMULATED scenarios (synthetic inputs, real pipeline) ---")
        scen = {}
        for k, sc in enumerate(["normal", "degraded", "emergency", "failure"]):
            e = build_simulated_events(1, scenario=sc, seed=a.seed + 100 + k)[0]
            if sc == "failure":
                e["simulate_failure"] = "cloud"
            r = c.post("/api/v1/events", json=e, headers=dev)
            r.raise_for_status()
            scen[sc] = (e, r.json())
            row(k + 1, f"simulated {sc}", r.json())
        b = scen["emergency"][1]
        checks.append(("emergency vitals -> EDGE override", b["decision"]["destination"] == "EDGE"
                       and b["decision"]["reason"] == "override_critical_patient", b["decision"]["reason"]))
        b = scen["degraded"][1]
        checks.append(("degraded network -> not CLOUD", b["decision"]["destination"] == "EDGE", b["decision"]["reason"]))
        ex = scen["failure"][1]["execution"]
        checks.append(("cloud failure -> fallback to EDGE recorded", ex["final_destination"] == "EDGE"
                       or ex["status"] in ("fallback", "failed"), f"{ex['status']} {ex['requested_destination']}->{ex['final_destination']}"))

        print("\n--- cloud AND edge adapters both fail ---")
        e = build_simulated_events(1, scenario="normal", seed=a.seed + 200)[0]
        e["simulate_failure"] = "both"
        r = c.post("/api/v1/events", json=e, headers=dev)
        bb = r.json() if r.status_code < 300 else {}
        print(f"    HTTP {r.status_code} status={bb.get('status')} execution={(bb.get('execution') or {}).get('status')}"
              f" error={(bb.get('execution') or {}).get('error')}")
        checks.append(("both adapters fail -> stored as failed, not lost", r.status_code in (201, 200, 502)
                       and (bb.get("execution") or {}).get("status") == "failed", f"HTTP {r.status_code}"))

        print("\n--- idempotency: re-send the same event_id ---")
        e0 = scen["normal"][0]
        r = c.post("/api/v1/events", json=e0, headers=dev)
        print(f"    HTTP {r.status_code} duplicate={r.json().get('duplicate')}")
        checks.append(("same event_id twice -> duplicate, no second execution", r.json().get("duplicate") is True, ""))

        print("\n--- invalid input is rejected (422) and nothing is stored ---")
        bad = copy.deepcopy(e0)
        bad["event_id"] = bad["event_id"] + "-bad"
        bad["network_window"] = bad["network_window"][:5]
        r = c.post("/api/v1/events", json=bad, headers=dev)
        print(f"    short window: HTTP {r.status_code}")
        checks.append(("window of 5 instead of 20 -> 422", r.status_code == 422, ""))
        bad2 = copy.deepcopy(e0)
        bad2["event_id"] = bad2["event_id"] + "-bad2"
        bad2["vitals"]["spo2"] = 140
        r2 = c.post("/api/v1/events", json=bad2, headers=dev)
        print(f"    SpO2 140 %:   HTTP {r2.status_code}")
        checks.append(("SpO2 140 -> 422", r2.status_code == 422, ""))
        missing = c.get(f"/api/v1/events/{bad['event_id']}", headers=adm).status_code
        checks.append(("rejected event not stored (GET -> 404)", missing == 404, f"HTTP {missing}"))

        print("\n--- authorisation ---")
        codes = {
            "no token -> POST /events": c.post("/api/v1/events", json=e0).status_code,
            "device -> GET /audit": c.get("/api/v1/audit", headers=dev).status_code,
            "device -> GET /events": c.get("/api/v1/events", headers=dev).status_code,
            "forged token -> GET /events": c.get("/api/v1/events", headers={"Authorization": "Bearer abc.def.ghi"}).status_code,
            "admin -> GET /audit": c.get("/api/v1/audit", headers=adm).status_code,
        }
        for k, v in codes.items():
            print(f"    {k:<32} HTTP {v}")
        checks += [("no token rejected", codes["no token -> POST /events"] == 401, ""),
                   ("device cannot read audit", codes["device -> GET /audit"] == 403, ""),
                   ("device cannot read records", codes["device -> GET /events"] == 403, ""),
                   ("forged token rejected", codes["forged token -> GET /events"] == 401, ""),
                   ("admin can read audit", codes["admin -> GET /audit"] == 200, "")]

        time.sleep(1.5)  # alerts are dispatched in the background after the response
        v = c.get("/api/v1/audit/verify", headers=adm).json()
        checks.append(("audit hash chain valid", v["valid"], f"{v['checked']} entries"))
        s = c.get("/api/v1/dashboard/summary", headers=adm).json()
        print("\n--- summary from GET /api/v1/dashboard/summary ---")
        for k in ("events", "decisions", "executions", "alerts"):
            if k in s:
                print(f"    {k}: {s[k]}")

    print("\n--- checks ---")
    for name, ok, info in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {info}")
    failed = [n for n, ok, _ in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
