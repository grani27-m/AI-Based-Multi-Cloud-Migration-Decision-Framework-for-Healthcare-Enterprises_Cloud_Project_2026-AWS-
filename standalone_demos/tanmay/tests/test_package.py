"""Tanmay package: fixtures reproduce the integrated system, scripts run, dashboard renders."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*a):
    return subprocess.run([sys.executable, *a], cwd=ROOT, capture_output=True, text=True, timeout=300)


def test_01_criteria_consistent_with_code():
    r = _run("01_load_criteria.py")
    assert r.returncode == 0 and "FAIL" not in r.stdout


def test_02_ahp_and_inconsistent_matrix():
    assert _run("02_calculate_ahp.py").returncode == 0
    bad = _run("02_calculate_ahp.py", "--matrix", "1,9,1/9;1/9,1,9;9,1/9,1")
    assert bad.returncode == 1 and "INCONSISTENT" in bad.stdout
    assert "INVALID MATRIX" in _run("02_calculate_ahp.py", "--matrix", "1,2;3,1").stdout


def test_03_reproduces_all_recorded_decisions():
    r = _run("03_compare_candidates.py")
    assert r.returncode == 0 and "127/127" in r.stdout


def test_04_explains_and_rejects():
    assert "DECISION: EDGE" in _run("04_explain_decision.py", "--vitals", "118,24,93", "--latency", "80", "--cost", "0.4").stdout
    assert "REJECTED" in _run("04_explain_decision.py", "--criticality", "3", "--latency", "nan").stdout


def test_dashboard_renders_and_reacts():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "05_dashboard.py"), default_timeout=120).run()
    assert not at.exception
    at.sidebar.slider[0].set_value(9.5).run()
    assert at.metric[0].value == "EDGE" and not at.exception
