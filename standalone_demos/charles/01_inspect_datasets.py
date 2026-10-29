"""
01 - Inspect the datasets shipped with this package (no download needed).

    python 01_inspect_datasets.py            # summary + checksum verification of every raw file
    python 01_inspect_datasets.py --quick    # skip re-hashing the 336 raw files

Shows sources and URLs, measurement IDs, probe IDs, time range, row counts, missing values and
quality checks, and verifies every raw RIPE Atlas file against the SHA-256 recorded at download.
Writes results/inspection_report.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict

from demo_common import META, RESULTS, ROOT, load_clean, measurements_meta, probes_meta, read_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    report: dict = {}
    print("=" * 78 + "\nRIPE Atlas network measurements (REAL data)\n" + "=" * 78)
    cfg = read_json(ROOT / "dataset/config/ripe_atlas_selection.json")
    print(f"API: {cfg['api_base']}   period: {cfg['time_range_utc']['start']} -> {cfg['time_range_utc']['stop']}")
    for m in measurements_meta():
        tag = "REJECTED " if m.get("rejected") else ""
        print(f"  {tag}msm {m['id']}: {m.get('type')} -> {m.get('target')}  interval {m.get('interval')} s"
              + (f"  ({m['reason'][:70]}...)" if m.get("rejected") else ""))
    probes = probes_meta()
    print(f"\nProbes ({len(probes)} selected):")
    for _, p in probes.iterrows():
        print(f"  {p['id']:>8}  {p['group']:<15} AS{p['asn_v4']:<7} {str(p['description'])[:45]}")

    manifest = [json.loads(line) for line in (META / "ripe_atlas_raw_manifest.jsonl").read_text().splitlines()]
    rows_by = defaultdict(int)
    for e in manifest:
        rows_by[(e["msm_id"], e["probe_id"])] += e["rows"]
    empty = sorted({p for (m, p), n in rows_by.items() if n == 0})
    print(f"\nRaw files: {len(manifest)} chunks, {sum(e['rows'] for e in manifest):,} raw results "
          f"(retrieved {min(e['retrieved_at'] for e in manifest)})")
    if empty:
        print(f"  probes that returned no results for a measurement: {empty}")

    if not a.quick:
        bad = 0
        for e in manifest:
            p = ROOT / e["file"]
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != e["sha256_file"]:
                bad += 1
                print("  CHECKSUM PROBLEM:", e["file"])
        print(f"Checksum verification: {len(manifest) - bad}/{len(manifest)} raw files match the download manifest")
        report["raw_checksums_ok"] = bad == 0

    q = read_json(META / "ripe_atlas_quality.json")
    print("\nCleaning (from dataset/metadata/ripe_atlas_quality.json):")
    for k in ("rows_raw", "rows_after_validity", "duplicates_removed", "rows_clean", "rows_total_loss",
              "rows_rtt_ge_150ms", "rows_rtt_ge_300ms", "series", "segments"):
        print(f"  {k:<22} {q[k]:>10,}")
    print(f"  invalid by reason      {q['invalid_by_reason']}")

    df = load_clean()
    print(f"\nProcessed table dataset/processed/ripe_atlas_clean.csv.gz: {len(df):,} rows x {df.shape[1]} columns")
    print("Missing values per column (NaN RTT = round with 100 % loss; NaN jitter = fewer than 2 replies):")
    for c, n in df.isna().sum().items():
        if c != "time_utc":
            print(f"  {c:<12} {n:>8,}")
    per = df.groupby(["msm_id", "prb_id"]).agg(rows=("timestamp", "size"), first=("time_utc", "min"),
                                               last=("time_utc", "max"), median_rtt=("rtt_avg_ms", "median"),
                                               loss_rounds=("rcvd", lambda s: int((s == 0).sum())))
    print("\nPer measurement x probe:")
    print(per.to_string())
    checks = {
        "row_count_matches_metadata": len(df) == q["rows_clean"],
        "no_duplicate_keys": not df.duplicated(["msm_id", "prb_id", "timestamp"]).any(),
        "rtt_order_min_avg_max": bool(((df.rtt_min_ms <= df.rtt_avg_ms) & (df.rtt_avg_ms <= df.rtt_max_ms) | df.rtt_avg_ms.isna()).all()),
        "loss_in_0_100": bool(df.loss_pct.between(0, 100).all()),
        "timestamps_in_period": bool(df.timestamp.min() >= 1788307200 and df.timestamp.max() < 1793145600),
    }
    print("\nQuality checks:")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")

    print("\n" + "=" * 78 + "\nPhysioNet BIDMC vital signs (REAL data, used only for patient criticality)\n" + "=" * 78)
    bm = read_json(META / "physionet_bidmc_manifest.json")
    ok = sum(f["checksum_matches_physionet"] for f in bm["files"])
    print(f"{bm['dataset']} - {bm['source']} - licence {bm['licence']}")
    print(f"{len(bm['files'])} numerics files, {ok} match PhysioNet SHA256SUMS; quality: {read_json(META / 'bidmc_quality.json')}")

    report.update({"rows_raw": q["rows_raw"], "rows_clean": len(df), "checks": checks, "bidmc_files": len(bm["files"]),
                   "bidmc_checksums_ok": ok == len(bm["files"])})
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "inspection_report.json").write_text(json.dumps(report, indent=2))
    print("\nwritten results/inspection_report.json")
    return 0 if all(checks.values()) and report.get("raw_checksums_ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
