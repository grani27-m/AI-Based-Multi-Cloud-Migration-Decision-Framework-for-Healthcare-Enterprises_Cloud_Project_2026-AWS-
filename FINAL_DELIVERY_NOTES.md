# Final delivery notes

## Contents of the ZIP
The complete repository **including its git history** (`.git`): baseline import + grouped commits per member area.
Excluded: `.env`, `node_modules/`, `frontend/dist/` (a prebuilt copy ships in `standalone_demos/rani/frontend/dist/`), `runtime/` (local DB, edge buffer), caches, and
`dataset/processed/windows_w20.npz` (rebuilt in ~20 s by `python -m src.prediction.dataset build`).

## Install · run · test · deploy
| Step | Command |
|---|---|
| Install | `pip install -r requirements-dev.txt` · `cd frontend && npm ci && npm run build` |
| Configure | `cp .env.example .env` and fill `SECRET_KEY`, `BOOTSTRAP_ADMIN_PASSWORD`, `DEVICE_PASSWORD` |
| Run | `uvicorn backend.app:create_app --factory --port 8000` → http://localhost:8000 |
| Demo data | `python -m scripts.create_user --username sim-device --role device --password-env DEVICE_PASSWORD`, then `python -m scripts.stream_events --mode replay --count 100` (or Admin → Demo runner in the UI) |
| Test | `pytest -q` (274 tests) |
| PostgreSQL | `docker compose up --build` |
| Load test | `python -m scripts.load_test --users 10 --requests 30` |
| AWS (eu-north-1) | staged guide `docs/AWS_DEPLOYMENT.md` — start with Stage 0 (read-only); the separate `hcf-aws-deploy-kit.zip` is what you upload to CloudShell |
| Each member alone | `standalone_demos/<member>/README.md` (numbered scripts, dashboard, tests) |
| Whole-project dashboard | run the API, open http://localhost:8000 → **Project tour** |
| Retrain | see README "Rebuild the data and the model" |

## What you must do yourselves
1. **Read `reports/TEAM_CONTRIBUTIONS.md`.** Each member must understand and be able to explain their files; follow your course's rules on declaring AI assistance.
2. **Update the PDF report** using `reports/FINAL_STATUS.md` §4 (the old dataset size, weights and test claims are wrong).
3. **Push to GitHub** with `docs/GITHUB_PUBLISHING.md` (CODEOWNERS routes each part to its owner for review).
4. **Run the AWS stages yourselves** (`docs/AWS_DEPLOYMENT.md`), one at a time, starting with read-only Stage 0.
5. Optional: Telegram bot token / Gmail app password for non-AWS alert channels; run CI on GitHub.

## Known limitations
See `reports/FINAL_STATUS.md` §2 and each member's README.
