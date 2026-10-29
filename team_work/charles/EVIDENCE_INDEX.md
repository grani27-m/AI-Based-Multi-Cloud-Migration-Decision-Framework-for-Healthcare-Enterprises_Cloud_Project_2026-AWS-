# Charles — evidence index
| Claim | Evidence |
|---|---|
| Real data acquired | `dataset/raw/ripe_atlas/` + `dataset/metadata/ripe_atlas_raw_manifest.jsonl` (URL, time, SHA-256 per chunk); `dataset/metadata/ripe_atlas_measurements.json`, `ripe_atlas_probes.json`; `dataset/metadata/physionet_bidmc_manifest.json` |
| Cleaning counts | `dataset/metadata/ripe_atlas_quality.json`, `bidmc_quality.json` |
| Splits | `dataset/metadata/ripe_atlas_splits.json` |
| Model selection | `results/model/experiments/experiment_log.json` (+ histories, v1 test metrics disclosed) |
| Test metrics | `results/model/metrics.json` |
| Graphs | `results/model/training_history.png`, `pred_vs_actual.png`, `baseline_comparison.png`; `results/screenshots/08_model_and_data.png` |
| Model in production path | every stored prediction has `method=lstm`, `model_version=lstm-20261029-0529` (`results/routing/evidence_run_summary.json`) |
| Tests | `results/tests/pytest_output.txt` |
