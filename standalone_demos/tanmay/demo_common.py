"""Helpers shared by Tanmay's demo scripts (package-only file)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
RESULTS = ROOT / "results"


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))
