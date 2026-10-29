# Model evaluation report — LSTM network-latency forecaster (Charles)

Source of every number: `results/model/metrics.json`, `results/model/experiments/experiment_log.json`,
`models/latency_lstm/preprocessing.json`. Reproduce:

```bash
pip install -r requirements-train.txt
python -m src.prediction.dataset build
python -m src.prediction.train --target-mode residual --loss huber --lr 1e-3 --epochs 20 --patience 3
python -m src.prediction.evaluate
```

## 1. Task
Forecast the next round-trip time (one RIPE Atlas interval = 240 s ahead) from the last 20 rounds of
`[rtt_avg, rtt_min, rtt_max, jitter, loss, hour_sin, hour_cos]` on real data (see `DATASET_REPORT.md`).

## 2. Model (architecture kept from the project report)
Input (20, 7) → LSTM 64 (return sequences) → Dropout 0.2 → LSTM 32 → Dropout 0.2 → Dense 16 ReLU → Dense 1.
31,393 parameters. RTT-type inputs are `log1p`-compressed and standardised with statistics from **training windows only**.
**Target:** `log1p(next RTT) − log1p(last RTT)` (residual), so an output of 0 equals the persistence forecast.

Serving uses a pure-numpy re-implementation of the same network (`NumpyLSTM`) loaded from `weights.npz`; a test asserts it
matches Keras within 1e-4. The API therefore needs no TensorFlow (inference ≈ 1 ms on CPU).

## 3. Model selection (validation set only)

| Run | Target | Loss | LR | Best epoch / run | Val MAE (ms) | Val persistence MAE |
|---|---|---|---|---|---|---|
| v1 | level | MSE | 1e-3 | 1 / 5 | — (val loss rose after epoch 1) | 1.817 |
| 2 | residual | MSE | 1e-3 | 10 / 13 | 1.578 | 1.817 |
| **3 (selected)** | **residual** | **Huber** | **1e-3** | **8 / 11** | **1.484** | 1.817 |
| 4 | residual | Huber | 3e-4 | 20 / 20 | 1.485 | 1.817 |

Disclosure: v1 was the first model trained and **was also evaluated on the test set** (MAE 2.076 ms vs persistence 1.633 ms,
i.e. worse than persistence on MAE; `experiments/v1_level_target_metrics.json`). That result motivated trying the residual
target. Runs 2–4 were compared on validation only; the test set was used once more, for the selected model.

v1 also had a structural flaw found later: as a level model trained on RTTs that are almost never above 150 ms, it saturates —
on simulated windows ending at 420–540 ms it predicted ≈200 ms, so **the 300 ms network veto could never have fired**.
The residual model predicts 400–511 ms on the same windows.

## 4. Held-out test results (2026-10-19 14:23 → 2026-10-27 23:59 UTC, 113,077 windows)

| Method | MAE (ms) | RMSE (ms) | MAE skill vs persistence | Risk-class accuracy |
|---|---|---|---|---|
| **LSTM (selected)** | **1.307** | 6.515 | **+20.0 %** | **99.04 %** |
| Persistence (next = last) | 1.633 | 7.994 | 0 | 98.75 % |
| Mean of last 20 | 1.781 | 6.688 | −9.1 % | 98.93 % |
| EWMA (α = 0.3) | 1.529 | **6.407** | +6.4 % | 99.03 % |
| Ridge regression (same inputs, residual target) | 1.496 | **6.407** | +8.4 % | 99.00 % |

* **Objective 1 of the report** ("held-out MAE and RMSE lower than a persistence baseline"): **met** (1.307 < 1.633 ms; 6.515 < 7.994 ms).
* The LSTM has the best MAE of all five methods, but **not the best RMSE**: EWMA and ridge are 0.11 ms lower. Large rare spikes
  dominate RMSE and no method predicts them well.
* Risk-class accuracy is high for every method because 98 %+ of rounds are LOW (< 75 ms); it is not a discriminating metric here.

### By probe group (MAE, ms)
| Group | Windows | LSTM | Persistence | EWMA | Ridge |
|---|---|---|---|---|---|
| Access networks (ISP/home) | 89,115 | **0.560** | 0.650 | 0.660 | 0.675 |
| Data-centre probes | 23,962 | **4.083** | 5.287 | 4.759 | 4.549 |

### Spike detection (does the forecast cross the threshold when the actual RTT does?)
| Threshold | Actual events in test | LSTM predicted / precision / recall | Persistence precision / recall |
|---|---|---|---|
| ≥ 150 ms (HIGH risk) | 29 | 20 / 0.85 / 0.59 | 0.69 / 0.69 |
| ≥ 300 ms (network veto) | **2** | 0 / — / 0.00 | 0.00 / 0.00 |

Only two test rounds reach 300 ms; no method anticipates them. The network veto is therefore validated with unit tests and
the labelled `degraded` simulator scenario, **not** with real-data recall.

## 5. Figures
`results/model/training_history.png`, `results/model/pred_vs_actual.png` (2 days of one access-network probe),
`results/model/baseline_comparison.png`; interactive versions on the dashboard's *Model & data* page.

## 6. Limitations
* One-step (240 s) horizon; the report's earlier "30 s ahead" wording does not apply to RIPE built-in pings.
* Pings to anycast root servers from Indian probes are a proxy for a hospital's path to its cloud region, not that path itself.
* Spikes ≥ 300 ms are too rare in 8 weeks of data to learn or evaluate; more data or targeted measurements would be needed.
* Small model, single seed (42); no confidence intervals were computed.
* The improvement over the simplest baselines is real but modest in absolute terms (0.2–0.3 ms MAE) because these paths are stable.
