"""
04 - Re-run the held-out evaluation and check it reproduces the reported metrics.

    python 04_evaluate_predictions.py          # needs dataset/processed/windows_w20.npz (run 02 first)

Runs src/prediction/evaluate.py (LSTM vs persistence, mean-of-20, EWMA, ridge on the SAME
113,077 test windows), regenerates results/model/*.png, and compares the new numbers with the
metrics shipped in this package.
"""

from __future__ import annotations

import json
import sys

from demo_common import ROOT


def main() -> int:
    windows = ROOT / "dataset/processed/windows_w20.npz"
    if not windows.exists():
        print("dataset/processed/windows_w20.npz missing - run: python 02_validate_and_preprocess.py")
        return 2
    shipped = json.loads((ROOT / "results/model/metrics.json").read_text())
    from src.prediction.evaluate import main as evaluate_main

    evaluate_main()
    new = json.loads((ROOT / "results/model/metrics.json").read_text())
    print(f"\n{'method':<12} {'shipped MAE':>12} {'rebuilt MAE':>12} {'shipped RMSE':>13} {'rebuilt RMSE':>13}")
    ok = True
    for k, v in shipped["overall"].items():
        n = new["overall"][k]
        same = abs(v["mae_ms"] - n["mae_ms"]) < 1e-3 and abs(v["rmse_ms"] - n["rmse_ms"]) < 1e-3
        ok &= same
        print(f"{k:<12} {v['mae_ms']:>12.4f} {n['mae_ms']:>12.4f} {v['rmse_ms']:>13.4f} {n['rmse_ms']:>13.4f}  {'OK' if same else 'DIFF'}")
    print(f"\nObjective 1 (LSTM beats persistence on MAE and RMSE): {new['objective_1_met']}")
    print("Metrics reproduced." if ok else "Metrics differ from the shipped file.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
