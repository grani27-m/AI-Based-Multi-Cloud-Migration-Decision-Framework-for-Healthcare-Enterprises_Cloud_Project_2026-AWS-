"""
standalone_demos/export.py
==========================
Copies the AUTHORITATIVE source files of the integrated project into each member's standalone
package, so a member can copy only `standalone_demos/<member>/` to a laptop and run it.

    python standalone_demos/export.py            # refresh all three packages
    python standalone_demos/export.py --check    # exit 1 if any exported copy differs from its source

Exported files are byte-identical copies; every package has EXPORTED_FILES.json listing source
path -> package path -> SHA-256. tests/unit/test_standalone_sync.py runs --check in the main
suite, so the copies cannot silently drift from the integrated project. Never edit an exported
file inside a package: edit the source file and re-run this script.
Files that exist ONLY in a package (numbered scripts, dashboards, READMEs, package tests) are
not touched by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent

INIT = ["src/__init__.py"]
PREDICTION_INFERENCE = [
    "src/prediction/__init__.py",
    "src/prediction/features.py",
    "src/prediction/model.py",
    "src/prediction/predict_service.py",
]
MODEL_ARTIFACTS = [
    "models/latency_lstm/weights.npz",
    "models/latency_lstm/preprocessing.json",
    "models/latency_lstm/training_history.json",
]
DECISION = [
    "src/decision/__init__.py",
    "src/decision/ahp.py",
    "src/decision/override_rules.py",
    "src/decision/router.py",
    "src/decision/criticality.py",
    "src/decision/candidates.py",
]

PACKAGES: dict[str, list[str]] = {
    "charles": INIT
    + PREDICTION_INFERENCE
    + [
        "src/prediction/ripe_parser.py",
        "src/prediction/dataset.py",
        "src/prediction/train.py",
        "src/prediction/evaluate.py",
        "data_ingestion/__init__.py",
        "data_ingestion/ripe_atlas.py",
        "data_ingestion/physionet_bidmc.py",
        "models/latency_lstm/model.keras",
        "tests/unit/test_prediction.py",
        "dataset/processed/ripe_atlas_clean.csv.gz",
        "results/model/metrics.json",
        "results/model/training_history.png",
        "results/model/pred_vs_actual.png",
        "results/model/baseline_comparison.png",
        "reports/DATASET_REPORT.md",
        "reports/MODEL_EVALUATION_REPORT.md",
    ]
    + MODEL_ARTIFACTS
    + ["dataset/config/**", "dataset/metadata/**", "dataset/raw/**", "results/model/experiments/**"],
    "tanmay": INIT
    + DECISION
    + [
        "infra/__init__.py",
        "infra/aws/__init__.py",
        "infra/aws/lambda_decision/__init__.py",
        "infra/aws/lambda_decision/handler.py",
        "tests/unit/test_decision.py",
        "tests/unit/test_candidates.py",
        "tests/unit/test_lambda_handler.py",
        "results/routing/weight_set_sensitivity.json",
        "results/routing/evidence_run_summary.json",
        "reports/ROUTING_EVALUATION_REPORT.md",
    ],
    "rani": INIT
    + PREDICTION_INFERENCE
    + DECISION
    + MODEL_ARTIFACTS
    + [
        "src/execution/__init__.py",
        "src/execution/adapters.py",
        "data_ingestion/__init__.py",
        "data_ingestion/replay.py",
        "data_ingestion/simulator.py",
        "dataset/samples/ripe_atlas_test_sample.csv.gz",
        "dataset/samples/bidmc_vitals_1hz.csv.gz",
        "dataset/metadata/ripe_atlas_splits.json",
        "dataset/metadata/ripe_atlas_quality.json",
        "dataset/metadata/bidmc_quality.json",
        "results/model/metrics.json",
        "alembic.ini",
        "scripts/__init__.py",
        "scripts/create_user.py",
        "scripts/stream_events.py",
        "scripts/load_test.py",
        "scripts/smoke_test.py",
        "scripts/mqtt_bridge.py",
        "infra/aws/service_status.json",
        "tests/conftest.py",
        "tests/unit/test_auth.py",
        "tests/unit/test_audit_alerts_execution.py",
        "tests/integration/test_api_pipeline.py",
        "tests/integration/test_persistence_and_migrations.py",
        "tests/integration/test_concurrency.py",
        "tests/integration/test_mqtt_bridge.py",
        "team_work/rani/SECURITY_NOTES.md",
        "integration/API_CONTRACT.md",
        "integration/DATABASE_SCHEMA.md",
        "architecture/ER_Diagram.png",
        "backend/**",
        "migrations/**",
        "frontend/dist/**",
    ],
}


def _expand(pattern: str) -> list[Path]:
    if pattern.endswith("/**"):
        base = ROOT / pattern[:-3]
        files = [p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        if not files:
            raise FileNotFoundError(f"nothing matches {pattern} (did you build frontend/dist?)")
        return sorted(files)
    p = ROOT / pattern
    if not p.is_file():
        raise FileNotFoundError(p)
    return [p]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def plan(member: str) -> list[tuple[Path, Path]]:
    pkg = HERE / member
    return [(src, pkg / src.relative_to(ROOT)) for pat in PACKAGES[member] for src in _expand(pat)]


def export(member: str) -> dict:
    pkg = HERE / member
    manifest_path = pkg / "EXPORTED_FILES.json"
    old = json.loads(manifest_path.read_text())["files"] if manifest_path.exists() else {}
    files = {}
    for src, dst in plan(member):
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or _sha(dst) != _sha(src):
            shutil.copy2(src, dst)
        files[str(dst.relative_to(pkg)).replace("\\", "/")] = {
            "source": str(src.relative_to(ROOT)).replace("\\", "/"),
            "sha256": _sha(src),
        }
    for stale in set(old) - set(files):  # file removed from the source/plan -> remove the old copy
        (pkg / stale).unlink(missing_ok=True)
    manifest = {
        "note": "Byte-identical copies of the integrated project's authoritative files. Do not edit here; "
        "edit the source and run `python standalone_demos/export.py`.",
        "files": dict(sorted(files.items())),
    }
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def check(member: str) -> list[str]:
    problems = []
    pkg = HERE / member
    manifest_path = pkg / "EXPORTED_FILES.json"
    if not manifest_path.exists():
        return [f"{member}: EXPORTED_FILES.json missing"]
    files = json.loads(manifest_path.read_text())["files"]
    expected = {str(d.relative_to(pkg)).replace("\\", "/"): s for s, d in plan(member)}
    for rel in sorted(set(expected) - set(files)):
        problems.append(f"{member}: {rel} not exported yet")
    for rel, meta in files.items():
        src = ROOT / meta["source"]
        dst = pkg / rel
        if not src.exists():
            problems.append(f"{member}: source {meta['source']} no longer exists")
        elif not dst.exists():
            problems.append(f"{member}: {rel} missing")
        elif _sha(dst) != _sha(src):
            problems.append(f"{member}: {rel} differs from {meta['source']}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("members", nargs="*", default=list(PACKAGES))
    a = ap.parse_args(argv)
    if a.check:
        problems = [p for m in a.members for p in check(m)]
        for p in problems:
            print("DRIFT:", p)
        print("standalone exports in sync" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    for m in a.members:
        n = len(export(m)["files"])
        print(f"{m}: {n} files exported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
