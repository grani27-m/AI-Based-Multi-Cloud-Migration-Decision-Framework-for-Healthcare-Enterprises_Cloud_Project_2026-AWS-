# Final verification report (29 Oct 2026)

What was run for this delivery, where, and with what result. Everything listed as "not verified" has not been run.

## 1. Integrated project (repository root)
| Check | Result | Evidence |
|---|---|---|
| `python -m pytest -q` | **274 passed** | rerun before packaging |
| `ruff check .` | all checks passed | |
| `cd frontend && npm run build` (tsc + vite) | build OK | `frontend/dist` → exported to `standalone_demos/rani/frontend/dist` |
| `python standalone_demos/export.py --check` | packages in sync with the authoritative files | `tests/unit/test_standalone_sync.py` |
| React portal against a live API (Playwright, 1440 px, light + dark) | 11 pages rendered, **0 browser errors** | `results/screenshots/final/*.png` |
| Production containers without AWS: release bundle → `Dockerfile.ec2` image → `docker-compose.prod.yml` + local-check override (PostgreSQL 16) | `/ready` true (database + model), one real replay event through LSTM → AHP → execution → PostgreSQL → audit chain valid; 204 MiB API + 60 MiB DB | `docs/AWS_DEPLOYMENT.md` §1 |
| CloudFormation `cfn-lint` (eu-north-1), `shellcheck` | 0 findings / 0 warnings | |

## 2. Standalone packages (each copied OUTSIDE the repository, new venv, `pip install -r requirements.txt`, Python 3.13)
| Package | Scripts | Tests | Dashboard | Report |
|---|---|---|---|---|
| Charles | 01–04 exit 0; counts and metrics reproduced from raw data | 25 passed, 1 skipped (TensorFlow absent) | Streamlit rendered (readings, relationship graph) | `standalone_demos/charles/TEST_REPORT.md` |
| Tanmay | 01–04 exit 0 (invalid input → exit 2, expected); 127/127 decisions reproduced | 184 passed | Streamlit rendered | `standalone_demos/tanmay/TEST_REPORT.md` |
| Rani | 00–06: execution demo 14/14 checks, tamper detected, persistence 6/6 | 69 passed | Streamlit (live API) and React portal rendered | `standalone_demos/rani/TEST_REPORT.md` |
Raw logs: `results/tests/standalone/`.

## 3. End-to-end chain demonstrated
Real RIPE Atlas window + real BIDMC vitals → LSTM forecast (`method=lstm`) → AHP + safety vetoes → execution adapter
(local stand-in; S3 adapter tested against a stub) → PostgreSQL/SQLite rows → hash-chained audit → alert (mock-labelled,
`mock_delivered`; webhook delivery evidence from the earlier run) → React and Streamlit dashboards reading the API.

## 4. Not verified
* AWS: nothing deployed; the staged guide must be executed by the team (`docs/AWS_DEPLOYMENT.md`).
* Real Telegram / e-mail / SNS delivery (needs your credentials or the AWS stack).
* GitHub Actions CI on GitHub's runners; Windows (packages tested on Linux; commands differ only in venv activation).
* Model retraining inside the packages (`03 --train`), last run in the main repository.
