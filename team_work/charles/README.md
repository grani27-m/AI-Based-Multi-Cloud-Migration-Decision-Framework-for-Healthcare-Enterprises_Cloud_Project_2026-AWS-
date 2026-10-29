# Charles Jehanabad (24BIT0522) — Datasets, preprocessing, LSTM latency prediction

**Role:** turn real network measurements into a trained, honestly evaluated forecaster, and provide the data streams
(replay of real data, labelled simulator) that drive the rest of the system.

## Run my part on its own
**Workstream:** A — Prediction & data pipeline (see `docs/WORKSTREAM_MAPPING.md`, every file's owner in `docs/FILE_OWNERSHIP_MATRIX.md`).

Standalone package: **`standalone_demos/charles/`** — copy the folder anywhere, `python -m venv .venv`, `pip install -r requirements.txt`, then
`01_inspect_datasets.py → 02_validate_and_preprocess.py → 03_train_or_load_model.py → 04_evaluate_predictions.py → streamlit run 05_dashboard.py`. Instructions: `standalone_demos/charles/README.md`. Verified outside the repository in a fresh environment:
25 passed + 1 skipped (TensorFlow not installed) — `standalone_demos/charles/TEST_REPORT.md`.


## Canonical source
| File | What it does |
|---|---|
| `data_ingestion/ripe_atlas.py` | `discover` / `download` / `verify`: measurement + probe metadata, weekly chunks per probe, retries/back-off, never overwrites, SHA-256 manifest |
| `dataset/config/ripe_atlas_selection.json` | the exact measurements (1001, 1004), 21 probes, period, selection rule, rejected candidate 228839605 |
| `data_ingestion/physionet_bidmc.py` | BIDMC download with PhysioNet checksum verification; cleaning of HR/RESP/SpO₂ |
| `src/prediction/ripe_parser.py` | one validated row per ping round; derived loss and jitter; invalid rows flagged with a reason |
| `src/prediction/features.py` | single feature definition shared by training and serving; scaler stored as JSON |
| `src/prediction/dataset.py` | cleaning counts, gap segmentation, chronological split, windowing |
| `src/prediction/model.py` | Keras stacked LSTM + numpy re-implementation for serving |
| `src/prediction/train.py` | training with early stopping; validation MAE in ms; artifacts + metadata |
| `src/prediction/evaluate.py` | test metrics vs persistence / mean / EWMA / ridge; by probe group; spike precision/recall; plots |
| `src/prediction/predict_service.py` | `LatencyPredictor` used by the API: validation, `lstm` or labelled `persistence_fallback` |
| `data_ingestion/replay.py`, `data_ingestion/simulator.py` | real-data replay events and labelled synthetic scenarios |
| `models/latency_lstm/` | `weights.npz`, `model.keras`, `preprocessing.json`, `training_history.json` |

## Run / test
```bash
pip install -r requirements-train.txt
python -m data_ingestion.ripe_atlas download && python -m data_ingestion.ripe_atlas verify
python -m data_ingestion.physionet_bidmc download && python -m data_ingestion.physionet_bidmc build
python -m src.prediction.dataset build
python -m src.prediction.train --target-mode residual --loss huber --lr 1e-3 --epochs 20 --patience 3
python -m src.prediction.evaluate
pytest tests/unit/test_prediction.py -q
```

## Results (details: `reports/DATASET_REPORT.md`, `reports/MODEL_EVALUATION_REPORT.md`)
* **756,495** real RIPE Atlas ping results downloaded (20 Indian probes returned data — 19 feed the model, probe 1000689 was 100 % loss — 2 measurements, 8 weeks) → **753,410** clean rows → 475k / 111k / 113k chronological windows.
* **53** real BIDMC ICU recordings, checksums verified.
* Held-out test: **LSTM MAE 1.307 ms vs persistence 1.633 ms (−20 %)**, RMSE 6.515 vs 7.994 ms → report Objective 1 met.
  EWMA and ridge have a slightly lower RMSE (6.407 ms); spikes ≥ 300 ms (2 in test) are not predicted by any method.
* The first model (absolute-level target) was worse than persistence on MAE and could not predict above ≈200 ms; it is kept in
  `results/model/experiments/` and disclosed.

## Integration contract
Input: 20 network observations; output `PredictionResult` (see `integration/API_CONTRACT.md` §2). Tanmay uses
`predicted_rtt_ms`; Rani persists the whole result, including `method` and `model_version`.

## Limitations
Anycast root-server pings are a proxy for a hospital-to-cloud path; one-step horizon; rare spikes; single seed;
bandwidth/signal strength are not available from RIPE Atlas and are no longer used.

## Definition of done
- [x] Real data downloaded with provenance, checksums, metadata, rebuild commands
- [x] No fabricated features; observed vs derived fields documented
- [x] Chronological split, no leakage, scaler on train only
- [x] LSTM trained on real data; artifacts saved with version and data hash
- [x] Compared with persistence and three other baselines on identical windows; Objective 1 met
- [x] Training and predicted-vs-actual graphs
- [x] Serving path verified equal to Keras; fallback explicitly labelled
- [ ] S3/SageMaker deployment (IaC uploads artifacts to S3 when deployed; SageMaker intentionally not used)
