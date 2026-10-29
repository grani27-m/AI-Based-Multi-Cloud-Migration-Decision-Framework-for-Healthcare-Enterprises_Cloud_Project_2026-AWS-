"""
src/prediction/model.py  —  Owner: Charles
===========================================
Two-layer stacked LSTM regressor (architecture kept from the project report):

    Input (20, 7) -> LSTM(64, return_sequences) -> Dropout(0.2)
                  -> LSTM(32) -> Dropout(0.2) -> Dense(16, relu) -> Dense(1)

Two implementations of the SAME network:
  * build_keras_model()   - TensorFlow/Keras, used for training (train.py).
  * NumpyLSTM             - pure-numpy forward pass that loads the exported weights.
                            Used by the API so the backend/Lambda does not need
                            TensorFlow. tests/unit/test_prediction.py checks that both give the
                            same output (tolerance 1e-4) for the saved model.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.prediction.features import FEATURES, WINDOW

UNITS = (64, 32)
DENSE = 16
DROPOUT = 0.2


def build_keras_model(lr: float = 1e-3, loss: str = "huber"):
    import tensorflow as tf
    from tensorflow import keras

    inp = keras.Input(shape=(WINDOW, len(FEATURES)), name="window")
    x = keras.layers.LSTM(UNITS[0], return_sequences=True, name="lstm_1")(inp)
    x = keras.layers.Dropout(DROPOUT, name="dropout_1")(x)
    x = keras.layers.LSTM(UNITS[1], name="lstm_2")(x)
    x = keras.layers.Dropout(DROPOUT, name="dropout_2")(x)
    x = keras.layers.Dense(DENSE, activation="relu", name="dense_relu")(x)
    out = keras.layers.Dense(1, name="output")(x)
    model = keras.Model(inp, out, name="latency_lstm")
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=lr),
                  loss=keras.losses.Huber(delta=1.0) if loss == "huber" else "mse",
                  metrics=[tf.keras.metrics.MeanAbsoluteError(name="mae")])
    return model


def export_numpy_weights(model, path: Path) -> None:
    """Save every layer's weights in a framework-independent .npz file."""
    w = {}
    for name in ("lstm_1", "lstm_2"):
        k, rk, b = model.get_layer(name).get_weights()
        w[f"{name}/kernel"], w[f"{name}/recurrent"], w[f"{name}/bias"] = k, rk, b
    for name in ("dense_relu", "output"):
        k, b = model.get_layer(name).get_weights()
        w[f"{name}/kernel"], w[f"{name}/bias"] = k, b
    np.savez(path, **w)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


class NumpyLSTM:
    """Inference-only re-implementation of the Keras graph (gate order i, f, c, o)."""

    def __init__(self, weights_path: Path):
        d = np.load(weights_path)
        self.w = {k: d[k].astype(np.float64) for k in d.files}

    def _lstm(self, x: np.ndarray, name: str, return_sequences: bool) -> np.ndarray:
        k, rk, b = self.w[f"{name}/kernel"], self.w[f"{name}/recurrent"], self.w[f"{name}/bias"]
        n = rk.shape[0]
        batch, steps, _ = x.shape
        h = np.zeros((batch, n))
        c = np.zeros((batch, n))
        seq = []
        for t in range(steps):
            z = x[:, t, :] @ k + h @ rk + b
            i, f, g, o = _sigmoid(z[:, :n]), _sigmoid(z[:, n:2 * n]), np.tanh(z[:, 2 * n:3 * n]), _sigmoid(z[:, 3 * n:])
            c = f * c + i * g
            h = o * np.tanh(c)
            if return_sequences:
                seq.append(h)
        return np.stack(seq, axis=1) if return_sequences else h

    def predict(self, x: np.ndarray) -> np.ndarray:
        """x: (batch, WINDOW, n_features) already scaled. Returns (batch,) scaled target."""
        x = np.asarray(x, dtype=np.float64)
        h = self._lstm(x, "lstm_1", True)
        h = self._lstm(h, "lstm_2", False)
        h = np.maximum(h @ self.w["dense_relu/kernel"] + self.w["dense_relu/bias"], 0.0)
        return (h @ self.w["output/kernel"] + self.w["output/bias"])[:, 0]
