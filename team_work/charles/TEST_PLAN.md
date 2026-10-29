# Charles — test plan (`pytest tests/unit/test_prediction.py`, 21 tests)
| Area | Tests |
|---|---|
| Parsing | valid ping; derived loss/jitter; total loss kept without RTT; invalid counts/RTT/errors/non-ping flagged |
| Honesty | no bandwidth/signal-strength features exist; fallback labelled `persistence_fallback` and equals last RTT |
| Features | forward/back fill; shape; hour-of-day encoding |
| Splits | windows never cross split boundaries or gaps; test strictly after train |
| Scaler | JSON round-trip |
| Service | rejects wrong length, unordered timestamps, loss > 100, missing RTT; risk class boundaries |
| Model | trained artifacts load (`lstm-…`), sensible output on a stable 30 ms path; **numpy == Keras within 1e-4** |
| Data quality (pipeline) | `data_ingestion.ripe_atlas verify` (336/336 checksums); BIDMC 53/53 PhysioNet checksums |
