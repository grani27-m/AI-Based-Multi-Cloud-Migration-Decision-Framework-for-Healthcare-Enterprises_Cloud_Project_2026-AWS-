# Charles — module inventory
| Path | Status vs received repo |
|---|---|
| `data_ingestion/ripe_atlas.py` | rewritten (old: 24 h of one ID, wrong labels, fabricated bandwidth/signal) |
| `data_ingestion/physionet_bidmc.py` | replaces `physionet.py` (never run) |
| `data_ingestion/replay.py`, `simulator.py` | new (simulator replaces `src/prediction/data_generator.py`, whose synthetic data was used as "training data") |
| `src/prediction/ripe_parser.py`, `features.py`, `dataset.py`, `evaluate.py` | new |
| `src/prediction/model.py` | architecture kept; numpy serving path added |
| `src/prediction/train.py` | rewritten (validation split, residual target, Huber, metadata) |
| `src/prediction/predict_service.py` | rewritten (old: silent `last × 1.1` reported as model output) |
| removed | `src/prediction/preprocessing.py` (device-ordered split), `src/ml_model/*` (duplicate) — kept in baseline commit |
| data | `dataset/raw/ripe_atlas/` (336 files), `dataset/raw/physionet_bidmc/` (53 files), `dataset/processed/ripe_atlas_clean.csv.gz`, `dataset/metadata/*`, `dataset/samples/*` |
| model | `models/latency_lstm/*`, `results/model/*` |
