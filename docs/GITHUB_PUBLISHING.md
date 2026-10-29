# Publishing to GitHub and showing each member's part

The team repository is `https://github.com/itscharles4/AI-Based-Multi-Cloud-Migration-Decision-Framework-for-Healthcare-Enterprises_Cloud_Project_2026`.
The ZIP contains this repository **with its git history** (`.git`), so nothing has to be re-committed by hand.

## Recommended: one integration pull request, reviewed per owner
```bash
unzip Healthcare-Cloud-Framework.zip && cd Healthcare-Cloud-Framework
git remote add origin https://github.com/itscharles4/AI-Based-Multi-Cloud-Migration-Decision-Framework-for-Healthcare-Enterprises_Cloud_Project_2026.git
git fetch origin
git checkout -b integration/v2
git push -u origin integration/v2
```
Then on GitHub open a pull request `integration/v2 → develop` (or `main`). Because of `.github/CODEOWNERS`, GitHub automatically
requests a review from **@itscharles4** for data/prediction files, **@TanmayKaps06** for the decision engine and **@grani27-m** for
the backend/UI/ops files. Each member reviews and approves their own part — that review is visible evidence of who owns what.
(The baseline commit in this ZIP is an import of the ZIP you supplied, so its hash differs from GitHub's history; GitHub will show the
branch as unrelated. If you prefer a clean merge: on a fresh clone of the GitHub repo, create the branch and copy the files of this
ZIP over it, then commit — `git add -A && git commit -m "Integrated v2"` — and open the PR the same way.)

## After merging: each member's own commits
The course asks for 20–30 commits per student on `feature/student1|2|3`. Those must be real work by that student, for example:
* Charles: rerun `python -m data_ingestion.ripe_atlas download` with a longer period, retrain, update `reports/MODEL_EVALUATION_REPORT.md`.
* Tanmay: add the planned sensitivity analysis of the 9.0 / 300 ms thresholds, add a second cloud alternative to the AHP.
* Rani: configure a real Telegram bot, deploy `infra/aws/` in Learner Lab, record evidence in `results/aws/`.
Commit from your own GitHub account on your feature branch and open PRs into `develop`.

## Never commit
`.env`, AWS keys, Telegram tokens, Gmail app passwords. `.gitignore` already excludes `.env` and `runtime/`.
