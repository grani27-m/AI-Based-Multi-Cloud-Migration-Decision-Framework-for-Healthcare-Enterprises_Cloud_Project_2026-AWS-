# Final delivery notes

## Contents of the ZIP
The complete repository **including its git history** (`.git`): baseline import + grouped commits per member area.
Excluded: `.env`, `node_modules/`, `frontend/dist/`, `runtime/` (local DB, edge buffer), caches, and
`dataset/processed/windows_w20.npz` (rebuilt in ~20 s by `python -m src.prediction.dataset build`).

## Install · run · test · deploy
| Step | Command |
|---|---|
| Install | `pip install -r requirements-dev.txt` · `cd frontend && npm ci && npm run build` |
| Configure | `cp .env.example .env` and fill `SECRET_KEY`, `BOOTSTRAP_ADMIN_PASSWORD`, `DEVICE_PASSWORD` |
| Run | `uvicorn backend.app:create_app --factory --port 8000` → http://localhost:8000 |
| Demo data | `python -m scripts.create_user --username sim-device --role device --password-env DEVICE_PASSWORD`, then `python -m scripts.stream_events --mode replay --count 100` (or Admin → Demo runner in the UI) |
| Test | `pytest -q` (122 tests) |
| PostgreSQL | `docker compose up --build` |
| Load test | `python -m scripts.load_test --users 10 --requests 30` |
| AWS | `bash infra/aws/deploy.sh` (your credentials) · `bash infra/aws/teardown.sh` |
| Retrain | see README "Rebuild the data and the model" |

## What you must do yourselves
1. **Read `reports/TEAM_CONTRIBUTIONS.md`.** Each member must understand and be able to explain their files; follow your course's rules on declaring AI assistance.
2. **Update the PDF report** using `reports/FINAL_STATUS.md` §4 (the old dataset size, weights and test claims are wrong).
3. **Push to GitHub** with `docs/GITHUB_PUBLISHING.md` (CODEOWNERS routes each part to its owner for review).
4. Optional, to close blocked items: Telegram bot token / Gmail app password (alerts), AWS Learner Lab (deploy script), run CI on GitHub.

## Known limitations
See `reports/FINAL_STATUS.md` §2 and each member's README.
