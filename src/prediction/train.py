"""
src/prediction/train.py  —  Owner: Charles
===========================================
Train the stacked LSTM on the REAL RIPE Atlas windows built by dataset.py.

    python -m src.prediction.train [--epochs 30] [--batch 512] [--seed 42]

Artifacts written to models/latency_lstm/
    model.keras            full Keras model (for retraining / SageMaker)
    weights.npz            framework-free weights used by the API (NumpyLSTM)
    preprocessing.json     features, window, scaler (fitted on TRAIN only), version, data hash
    training_history.json  per-epoch loss/MAE on train and validation
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.prediction.features import FEATURES, TARGET, WINDOW, Scaler, last_log_rtt, target_from_model
from src.prediction.model import DENSE, DROPOUT, UNITS, build_keras_model, export_numpy_weights

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "dataset" / "processed" / "windows_w20.npz"
OUT = ROOT / "models" / "latency_lstm"
log = logging.getLogger("train")


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--patience", type=int, default=4)
    ap.add_argument("--target-mode", choices=["level", "residual"], default="residual")
    ap.add_argument("--loss", choices=["mse", "huber"], default="huber")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    out_dir = Path(a.out)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import tensorflow as tf
    tf.keras.utils.set_random_seed(a.seed)

    d = np.load(WINDOWS)
    Xtr, ytr, Xva, yva = d["X_train"], d["y_train"], d["X_val"], d["y_val"]
    if a.target_mode == "residual":  # predict change of log-RTT relative to the last observation
        ytr = (ytr - last_log_rtt(Xtr)).astype(np.float32)
        yva = (yva - last_log_rtt(Xva)).astype(np.float32)
    log.info("train windows %s  val windows %s  target=%s loss=%s lr=%g", Xtr.shape, Xva.shape,
             a.target_mode, a.loss, a.lr)
    scaler = Scaler.fit(Xtr.reshape(-1, Xtr.shape[-1]), ytr)  # TRAIN ONLY
    Xtr_s, Xva_s = scaler.x(Xtr), scaler.x(Xva)
    ytr_s, yva_s = scaler.y(ytr), scaler.y(yva)

    model = build_keras_model(lr=a.lr, loss=a.loss)
    cb = [tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=a.patience, restore_best_weights=True)]
    t0 = time.time()
    hist = model.fit(Xtr_s, ytr_s, validation_data=(Xva_s, yva_s), epochs=a.epochs, batch_size=a.batch,
                     shuffle=True, callbacks=cb, verbose=2)
    secs = time.time() - t0

    # validation MAE in milliseconds (model selection uses VALIDATION only, never test)
    pv = scaler.y_inverse(model.predict(Xva_s, batch_size=4096, verbose=0)[:, 0])
    if a.target_mode == "residual":
        pv = pv + last_log_rtt(Xva)
    val_mae_ms = float(np.mean(np.abs(target_from_model(pv) - d["y_ms_val"])))
    val_pers_ms = float(np.mean(np.abs(d["last_ms_val"] - d["y_ms_val"])))
    log.info("validation MAE %.3f ms (persistence %.3f ms)", val_mae_ms, val_pers_ms)

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save(out_dir / "model.keras")
    export_numpy_weights(model, out_dir / "weights.npz")
    best = int(np.argmin(hist.history["val_loss"]))
    version = datetime.now(timezone.utc).strftime("lstm-%Y%m%d-%H%M")
    meta = {
        "model_version": version,
        "architecture": {"type": "stacked LSTM", "units": UNITS, "dense": DENSE, "dropout": DROPOUT,
                         "params": int(model.count_params())},
        "window": WINDOW, "features": FEATURES, "target_mode": a.target_mode,
        "target": f"next {TARGET}: log1p, " + ("minus log1p(last RTT), " if a.target_mode == "residual" else "")
                  + "standardised",
        "horizon": "one measurement interval (240 s for RIPE Atlas built-in pings)",
        "scaler": scaler.to_dict(), "scaler_fitted_on": "training windows only",
        "training": {"epochs_run": len(hist.history["loss"]), "best_epoch": best + 1, "batch": a.batch,
                     "seed": a.seed, "optimizer": f"Adam({a.lr:g})", "loss": a.loss,
                     "val_mae_ms": val_mae_ms, "val_persistence_mae_ms": val_pers_ms, "seconds": round(secs, 1),
                     "train_windows": int(len(ytr)), "val_windows": int(len(yva)),
                     "tensorflow": tf.__version__},
        "data": {"windows_file": str(WINDOWS.relative_to(ROOT)), "windows_sha256": file_sha256(WINDOWS),
                 "source": "RIPE Atlas built-in pings msm 1001/1004, see dataset/metadata"},
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out_dir / "preprocessing.json").write_text(json.dumps(meta, indent=2))
    (out_dir / "training_history.json").write_text(json.dumps(
        {k: [float(v) for v in vals] for k, vals in hist.history.items()}, indent=2))
    log.info("saved %s (best epoch %d, %.0fs)", version, best + 1, secs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
