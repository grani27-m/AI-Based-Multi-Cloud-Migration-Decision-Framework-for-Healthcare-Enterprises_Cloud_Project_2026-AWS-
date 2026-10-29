"""Charles package: shipped data integrity, numbered scripts and dashboard (package-only tests)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_raw_files_match_download_manifest():
    lines = (ROOT / "dataset/metadata/ripe_atlas_raw_manifest.jsonl").read_text().splitlines()
    entries = [json.loads(x) for x in lines]
    assert len(entries) == 336
    for e in entries:
        assert hashlib.sha256((ROOT / e["file"]).read_bytes()).hexdigest() == e["sha256_file"], e["file"]
    assert sum(e["rows"] for e in entries) == 756495


def test_bidmc_files_present_and_verified():
    m = json.loads((ROOT / "dataset/metadata/physionet_bidmc_manifest.json").read_text())
    assert len(m["files"]) == 53 and all(f["checksum_matches_physionet"] for f in m["files"])
    for f in m["files"]:
        assert hashlib.sha256((ROOT / f["file"]).read_bytes()).hexdigest() == f["sha256"]


def _run(*args, timeout=600):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def test_01_inspect_quick():
    r = _run("01_inspect_datasets.py", "--quick")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "[PASS] row_count_matches_metadata" in r.stdout


def test_03_inference_only():
    r = _run("03_train_or_load_model.py")
    assert r.returncode == 0, r.stderr[-2000:]
    assert "inference-only" in r.stdout and "series test MAE" in r.stdout


def test_dashboard_renders_without_errors():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "05_dashboard.py"), default_timeout=300).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(m.label == "Clean rows" and m.value == "753,410" for m in at.metric)
    at.sidebar.selectbox[1].set_value(1003379).run()
    assert not at.exception
