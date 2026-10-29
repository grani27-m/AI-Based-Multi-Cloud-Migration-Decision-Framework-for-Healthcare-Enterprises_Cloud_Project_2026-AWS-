# Test report — Tanmay's standalone package

**Run:** 29 Oct 2026, committed files copied **outside the repository**, new virtual environment, `pip install -r requirements.txt`.
Python 3.13.18, Linux x86_64; numpy 2.5.4, pandas 3.1.0, streamlit 1.66.1, plotly 6.9.0, pytest 9.2.0.
Full log: `results/tests/standalone/tanmay.log` in the integrated repository.

| Step | Result |
|---|---|
| `python 01_load_criteria.py` | exit 0 — criteria file matches the code |
| `python 02_calculate_ahp.py` | exit 0 — weights 0.6370 / 0.2583 / 0.1047, CR 0.0332 |
| `python 03_compare_candidates.py` | exit 0 — 127/127 exported pipeline decisions reproduced |
| `python 04_explain_decision.py --vitals 118,24,93 --latency 80 --cost 0.4` | exit 0 — full explanation |
| `python 04_explain_decision.py --criticality 3 --cloud mumbai:30:0.5 --cloud stockholm:150:0.2 --cloud far:320:0.1` | exit 0 — ranking, `far` excluded by the 300 ms veto |
| `python 04_explain_decision.py --criticality 3 --latency nan` | exit 2 — **expected**: invalid input rejected, no decision |
| `python -m pytest tests -q` | **184 passed** |
| `streamlit run 05_dashboard.py` | renders; screenshot `results/screenshots/final/standalone_tanmay_dashboard.png` |
