# Charles Jehanabad (24BIT0522) — Real network data & LSTM latency prediction (standalone demo)

This folder runs **on its own**: copy it to any laptop, install, run. It does not need the backend, the database,
Tanmay's or Rani's code, or an internet connection (except to download *more* data).

| What | Where | Real or not |
|---|---|---|
| 336 raw RIPE Atlas result files (756,495 ping results, msm 1001 & 1004, 21 Indian probes, 2 Sep – 28 Oct 2026) | `dataset/raw/ripe_atlas/` | **REAL**, SHA-256 per file in `dataset/metadata/ripe_atlas_raw_manifest.jsonl` |
| 53 PhysioNet BIDMC ICU numerics files | `dataset/raw/physionet_bidmc/` | **REAL**, checksums match PhysioNet |
| Cleaned table (753,410 rows) | `dataset/processed/ripe_atlas_clean.csv.gz` | derived from the raw files (rebuild with 02) |
| Trained model `lstm-20261029-0529` | `models/latency_lstm/` | trained on the real windows; `model.keras` + numpy weights |
| Test metrics, plots, experiment log | `results/model/` | produced by `src/prediction/evaluate.py` |

Probe 1000689 (OVH data centre) reported 100 % packet loss to both targets in every round, so it has rows but no RTT
values and contributes **no training windows** — 19 probes actually feed the model.

## Setup (Windows PowerShell; macOS/Linux identical except the activate line)
Python **3.11–3.13** (tested on 3.13).
```powershell
cd charles
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Demo — numbered steps
| Step | Command | Time | What you see |
|---|---|---|---|
| 1 | `python 01_inspect_datasets.py` | ~15 s | measurements, probes, raw-file checksum verification (336/336), cleaning counts, missing values, per-probe rows/time range, quality checks, BIDMC verification |
| 2 | `python 02_validate_and_preprocess.py` | ~30 s, 2 GB RAM | rebuilds the clean table and the train/validation/test windows **from the raw JSON** and checks every count matches |
| 3 | `python 03_train_or_load_model.py` | ~5 s | **inference-only mode**: loads the verified model (no TensorFlow), shows its metadata and real held-out predictions vs actual vs persistence |
| 3b | `pip install -r requirements-train.txt` then `python 03_train_or_load_model.py --train` | ~12 min (2 CPUs) | retrains into `models/latency_lstm_retrained/` (the verified model is not overwritten) |
| 4 | `python 04_evaluate_predictions.py` (after step 2) | ~1 min | re-runs the held-out evaluation and checks the numbers match the shipped `metrics.json` |
| 5 | `streamlit run 05_dashboard.py` | opens http://localhost:8501 | interactive dashboard (below) |

### Dashboard tabs
* **Readings** — pick a measurement and probe in the sidebar; 8 weeks of real RTT (min/avg/max) with the train / validation /
  test periods shaded, hourly packet loss, raw rows.
* **Prediction vs actual** — the shipped LSTM runs live on the selected series; actual vs LSTM vs persistence for the chosen
  split, with per-split MAE/RMSE for that series.
* **Model evaluation** — the held-out test table (LSTM vs 4 baselines), by probe group, training history, model-selection log.
* **Relationship graph** — measurements → targets → probes → networks (ASNs) → probe groups. Click a node (or pick it in the
  list) to highlight its connections and see its real metadata and row counts.
* **Data sources & quality** — measurement/probe metadata, cleaning counts, missing values, window counts.

## Tests
```powershell
python -m pytest tests -q
```
26 tests: parser, features, chronological windows (no leakage), scaler, labelled fallback, model loading, numpy-vs-Keras
equality (skipped when TensorFlow is absent), all 336 raw checksums, BIDMC checksums, scripts 01/03, dashboard rendering.

## Headline results (from `results/model/metrics.json`)
Held-out test (19–27 Oct 2026, 113,077 windows): **LSTM MAE 1.307 ms vs persistence 1.633 ms (−20 %)**, RMSE 6.515 vs
7.994 ms. EWMA and ridge reach a slightly lower RMSE (6.407 ms); RTT spikes ≥ 300 ms (2 in the test period) are not predicted
by any method. Full discussion: `reports/MODEL_EVALUATION_REPORT.md`.

## How this connects to the integrated project
These files are **byte-identical copies** of the integrated project's `src/prediction/`, `data_ingestion/`, `dataset/` and
`models/` (listed with hashes in `EXPORTED_FILES.json`). The integrated API calls the same `LatencyPredictor.predict()` that
step 3 uses. Do not edit copied files here; change them in the main repository and re-export.

## Limitations
Anycast root-server pings are a proxy for a hospital-to-cloud path; 240 s horizon; rare spikes; single training seed.
