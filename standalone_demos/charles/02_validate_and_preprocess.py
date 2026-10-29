"""
02 - Rebuild the processed dataset from the RAW files and check it reproduces the shipped numbers.

    python 02_validate_and_preprocess.py

Runs the same code as the integrated project (src/prediction/dataset.py): parse every raw ping
result, validate, deduplicate, segment, build chronological train/validation/test windows.
Output: dataset/processed/ripe_atlas_clean.csv.gz, dataset/processed/windows_w20.npz,
dataset/metadata/ripe_atlas_quality.json and ripe_atlas_splits.json. ~30 s, ~2 GB RAM.
Then compares the new counts with the counts recorded when the dataset was first built.
"""

from __future__ import annotations

import json
import logging

from demo_common import META, ROOT  # noqa: F401  (sets sys.path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    before_q = json.loads((META / "ripe_atlas_quality.json").read_text())
    before_s = json.loads((META / "ripe_atlas_splits.json").read_text())
    from src.prediction.dataset import build

    q = build()
    s = json.loads((META / "ripe_atlas_splits.json").read_text())
    print("\nReproducibility check (shipped -> rebuilt):")
    ok = True
    for k in ("rows_raw", "rows_clean", "rows_total_loss", "duplicates_removed", "series", "segments"):
        same = before_q[k] == q[k]
        ok &= same
        print(f"  [{'SAME' if same else 'DIFF'}] {k:<20} {before_q[k]:>10,} -> {q[k]:>10,}")
    for k in ("train", "val", "test"):
        same = before_s["windows"][k] == s["windows"][k]
        ok &= same
        print(f"  [{'SAME' if same else 'DIFF'}] {k + ' windows':<20} {before_s['windows'][k]:>10,} -> {s['windows'][k]:>10,}")
    print("All counts reproduced." if ok else "Counts differ - inspect dataset/metadata/*.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
