"""The standalone member packages must contain byte-identical copies of the authoritative source files."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_standalone_exports_are_in_sync():
    r = subprocess.run([sys.executable, str(ROOT / "standalone_demos" / "export.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
