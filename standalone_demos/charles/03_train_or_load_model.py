"""
03 - Load the verified trained model (default, inference-only) or retrain it.

    python 03_train_or_load_model.py                 # INFERENCE-ONLY: load models/latency_lstm (numpy, no TensorFlow)
    python 03_train_or_load_model.py --train         # retrain (needs requirements-train.txt + 02 first), ~12 min on 2 CPUs
                                                     #   -> models/latency_lstm_retrained/ (the verified model is NOT overwritten)

Inference-only mode runs the exported weights through the pure-numpy LSTM - the same code the
integrated API uses - on real held-out test windows and prints a few predictions.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

from demo_common import MODEL_DIR, ROOT, load_clean, predict_series, read_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    a = ap.parse_args()
    if a.train:
        try:
            import tensorflow  # noqa: F401
        except ImportError:
            print("TensorFlow is not installed. Run: pip install -r requirements-train.txt\n"
                  "(Inference-only mode works without it: python 03_train_or_load_model.py)")
            return 2
        if not (ROOT / "dataset/processed/windows_w20.npz").exists():
            print("windows_w20.npz missing - run python 02_validate_and_preprocess.py first")
            return 2
        from src.prediction.train import main as train_main

        return train_main(["--target-mode", "residual", "--loss", "huber", "--lr", "1e-3", "--epochs", "20",
                           "--patience", "3", "--out", str(ROOT / "models" / "latency_lstm_retrained")])

    meta = read_json(MODEL_DIR / "preprocessing.json")
    tr = meta["training"]
    print("MODE: inference-only (verified artifacts, numpy forward pass, TensorFlow not required)")
    print(f"model_version  {meta['model_version']}   trained {meta['trained_at']}")
    print(f"architecture   {meta['architecture']}")
    print(f"features       {meta['features']}  window {meta['window']}  target {meta['target']}")
    print(f"training       best epoch {tr['best_epoch']}/{tr['epochs_run']}, loss {tr['loss']}, {tr['optimizer']}, "
          f"train windows {tr['train_windows']:,}, val windows {tr['val_windows']:,}")
    print(f"validation     MAE {tr['val_mae_ms']:.3f} ms vs persistence {tr['val_persistence_mae_ms']:.3f} ms")
    print(f"data hash      {meta['data']['windows_sha256'][:16]}... (windows file the model was trained on)")

    df = load_clean()
    sid = "1001-25250"
    s = df[df.series_id == sid]
    p = predict_series(s)
    t = p[p.split == "test"].tail(8)
    print(f"\nLast 8 held-out TEST predictions for series {sid} (probe 25250, k-root):")
    print(t[["time_utc", "actual_ms", "lstm_ms", "persistence_ms"]].round(2).to_string(index=False))
    test = p[p.split == "test"]
    if len(test):
        print(f"\nseries test MAE: LSTM {np.mean(np.abs(test.lstm_ms - test.actual_ms)):.3f} ms, "
              f"persistence {np.mean(np.abs(test.persistence_ms - test.actual_ms)):.3f} ms ({len(test):,} windows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
