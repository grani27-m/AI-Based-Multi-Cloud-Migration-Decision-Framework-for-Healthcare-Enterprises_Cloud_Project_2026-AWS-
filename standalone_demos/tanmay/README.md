# Tanmay Kapoor (24BIT0079) — AHP decision engine (standalone demo)

Runs **on its own**: no backend, no database, no model, no internet. The engine itself is pure Python.

## Setup
Python **3.10–3.13** (tested 3.13).
```powershell
cd tanmay
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Demo — numbered steps
| Step | Command | What you see |
|---|---|---|
| 1 | `python 01_load_criteria.py` | the three criteria, units, normalisation, pairwise matrix, thresholds; checks `data/criteria.json` = the code |
| 2 | `python 02_calculate_ahp.py` | power iteration step by step → weights **0.6370 / 0.2583 / 0.1047**, λmax 3.0385, CI, **CR 0.0332** (0.037 with RI 0.52); comparison with the old code and the report's printed weights |
| 2b | `python 02_calculate_ahp.py --matrix "1,9,1/9;1/9,1,9;9,1/9,1"` | an inconsistent matrix is detected (CR 6.13) |
| 3 | `python 03_compare_candidates.py` | recomputes **127 decisions** exported from the integrated system and confirms **127/127 identical**; ranks an edge node against three clouds |
| 4 | `python 04_explain_decision.py --vitals 118,24,93 --latency 80 --cost 0.4` | full explanation: NEWS2 points → criticality, normalised inputs, contribution table, scores, decision |
| 4b | `python 04_explain_decision.py --criticality 3 --cloud "mumbai:30:0.5" --cloud "stockholm:150:0.2" --cloud "far:320:0.1"` | multi-cloud ranking with a vetoed cloud |
| 4c | `python 04_explain_decision.py --criticality 3 --latency nan` | invalid input → explicit rejection, no decision |
| 5 | `streamlit run 05_dashboard.py` | interactive dashboard (http://localhost:8501) |

### Dashboard
* **Decision** — sliders (or vitals → partial NEWS2, or a cached pipeline event), weight-set choice; destination, reason,
  scores, normalisation/contribution table, and a **decision-flow graph** (inputs → vetoes / criteria with weights →
  EDGE/CLOUD with contribution-weighted edges → decision). Click a node (or pick it) to see its numbers.
* **Multi-cloud ranking** — editable table of cloud destinations; ranking, exclusions (vetoes), scores.
* **AHP weights & consistency** — matrix, three weight sets, λmax, CI, CR.
* **Sensitivity map** — destination over criticality × latency.
* **Cached events** — the 127 exported events with recomputed vs recorded destination.

## Data in this package
| File | Content | Real or not |
|---|---|---|
| `data/criteria.json` | criteria, matrix, thresholds | configuration (checked against code) |
| `data/sample_events.json` | 127 events exported from the integrated system's evidence run: LSTM forecasts and criticality | `source=replay`: **real** RIPE Atlas test-period windows → real LSTM forecasts, **real** BIDMC vitals; `source=simulated`: simulated inputs; cost index synthetic everywhere |
| `data/candidates_example.json` | multi-cloud example | **hypothetical** values |

## Tests
```powershell
python -m pytest tests -q          # 184 tests (37 engine, 139 multi-cloud incl. 126-case equivalence, 3 Lambda, 5 package)
```

## Relation to the integrated project
`src/decision/*` and `infra/aws/lambda_decision/handler.py` are byte-identical copies of the integrated project's files
(`EXPORTED_FILES.json`). The integrated API calls the same `decide()` for every stored event, exposes it as
`POST /api/v1/decision/preview` and the multi-cloud ranking as `POST /api/v1/decision/rank`.

## Limitations
Thresholds and weights are design parameters, not clinically validated; the squared-criticality aggregation is a team design
choice, not standard additive AHP; the multi-cloud candidates in the demo are hypothetical (no second provider is measured).
