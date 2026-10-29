# Routing evaluation report (Tanmay's engine inside Rani's pipeline)

Evidence: `results/routing/evidence_run_summary.json` (a live API run over HTTP on a fresh database),
`results/routing/weight_set_sensitivity.json`, logs in `results/logs/stream_*.log`.

## 1. Evidence run (2026-10-29)
A fresh API instance (SQLite, selected LSTM `lstm-20261029-0529`, webhook alert channel pointing to a local receiver) received,
**over HTTP with a device JWT**:

| Stream | Events | EDGE | Reasons | Execution | Alerts |
|---|---|---|---|---|---|
| **Replay — real RIPE Atlas test-period windows + real BIDMC vitals** | 400 | **13 (3.2 %)** | AHP 400 | 400 success | none |
| Simulated `normal` | 25 | 0 | AHP 25 | success | — |
| Simulated `degraded` (RTT ramps to 400–600 ms) | 20 | 20 | **network veto 20** | success | 20 WARNING (recorded, not pushed) |
| Simulated `emergency` (critical vitals) | 12 | 12 | **emergency override 12** | success | 12 CRITICAL, **12 delivered** (webhook HTTP 200) |
| Simulated `failure` (cloud fault injected) | 10 | 0 → executed at EDGE | AHP 10 | **10 fallback_success** (3 cloud attempts + edge) | — |
| **Total** | **467** | 45 | override 12 · veto 20 · AHP 435 · safe-default 0 | 457 success · 10 fallback | 32 triggered · 12 delivered · 20 not notified |

Reconciliation (from the summary endpoint): events = Σ statuses; Σ reasons = decisions (467 = 12 + 20 + 435);
events = decisions + failed-before-decision (0) + in-flight (0); audit chain valid (1,008 entries).
The old report's defect — 518 events vs 500 reason counts, "32 alerts" = 32 overrides — cannot recur: every number is a
query on stored rows, and triggered/delivered are separate.

## 2. What happens on real data
* **Criticality from real ICU vitals** (partial NEWS2 on BIDMC) in the 400 replayed events: 0.0 ×152, 1.43 ×103, 2.86 ×70,
  4.29 ×43, 5.71 ×10, 7.14 ×16, 8.57 ×6.
* Across **all 25,485 BIDMC seconds** the partial NEWS2 aggregate never exceeds 6 (criticality 8.57), so **the emergency
  override (≥ 9.0) never fires on these real recordings**. The 13 EDGE decisions on replayed data come from AHP scoring of
  criticality 7.14 and 8.57 (squared-criticality term).
* **Forecast RTT** on replayed data: median 14.8 ms, max 130.9 ms; risk LOW 385, MEDIUM 15, HIGH 0 → **no network veto** on real
  data. In the full dataset only 47 of 753,410 rounds reach 300 ms.
* Conclusion: with real Indian broadband/data-centre paths and real ICU vitals, the engine sends ~97 % of readings to the cloud,
  and the safety vetoes are dormant. Their correct behaviour is demonstrated by the labelled simulator scenarios and unit tests.

## 3. Weight-set sensitivity
On an 11,880-point grid of non-veto inputs (criticality 0–8.75, latency 0–290 ms, cost 0–1):

| Weight set | EDGE share | Decisions differing from eigenvector | Criticality at which EDGE starts (40 ms, cost 0.3) |
|---|---|---|---|
| Eigenvector (used) | 33.66 % | — | 7.04 |
| Printed in report | 33.64 % | 14 (0.12 %) | 7.02 |
| Column normalisation (old code) | 33.66 % | 16 (0.13 %) | 7.07 |

The report's unreproducible weights change practically nothing.

## 4. Baseline policies (report §10.3 — partly evaluated)
Measured on the same 400 replayed real events (computed from the stored records):

| Policy | EDGE | Disagreements with the engine |
|---|---|---|
| Proposed engine (vetoes + AHP) | 13 | — |
| Always-cloud | 0 | 13 |
| Fixed threshold (EDGE if forecast > 100 ms or criticality > 9) | 10 | 23 |

The fixed rule moves readings to the edge whenever the *network* is slower than 100 ms, regardless of the patient (10 events with
forecasts of 119–131 ms and criticality ≤ 4.29, which the engine sent to the cloud), while the engine keeps the *serious-but-not-emergency* patients (criticality 7.14–8.57) local and lets
moderately slow but routine traffic go to the cloud. Which is "better" needs a clinical cost model; this report only shows that
the policies differ and how. A larger comparison on more varied data is future work.

## 5. Limitations
* The network path and the patient in a replay event are paired artificially; the cost index is a synthetic tariff proxy.
* Thresholds (9.0, 300 ms) and the squared-criticality formula are design parameters without clinical validation.
* "Multi-cloud": only one cloud alternative is scored.
