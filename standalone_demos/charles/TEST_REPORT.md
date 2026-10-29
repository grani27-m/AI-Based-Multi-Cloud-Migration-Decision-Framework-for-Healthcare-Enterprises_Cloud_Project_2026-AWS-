# Test report — Charles's standalone package

**Run:** 29 Oct 2026, the package's committed files copied to a folder **outside the repository**, new virtual environment,
`pip install -r requirements.txt` only (no TensorFlow). Python 3.13.18, Linux x86_64; numpy 2.5.4, pandas 3.1.0,
scikit-learn 1.9.1, streamlit 1.66.1, plotly 6.9.0, pytest 9.2.0. Full log: `results/tests/standalone/charles.log` in the
integrated repository.

| Step | Result |
|---|---|
| `python 01_inspect_datasets.py` | exit 0 — 336/336 raw-file checksums match, quality checks pass, 53 BIDMC files verified |
| `python 02_validate_and_preprocess.py` | exit 0 — "All counts reproduced." (753,410 clean rows; 475,196 / 111,314 / 113,077 windows) |
| `python 03_train_or_load_model.py` | exit 0 — inference-only mode, model `lstm-20261029-0529` loaded with NumPy |
| `python 04_evaluate_predictions.py` | exit 0 — "Metrics reproduced." (LSTM MAE 1.307 ms vs persistence 1.633 ms) |
| `python -m pytest tests -q` | **25 passed, 1 skipped** (the NumPy-vs-Keras equality test is skipped because TensorFlow is not installed; it passes in the main repository where TensorFlow is present) |
| `streamlit run 05_dashboard.py` | renders; screenshots `results/screenshots/final/standalone_charles_*.png` |

Not tested here: `03 --train` (needs `requirements-train.txt`, ~12 min); Windows was not available — commands are the same
except the venv activation line.
