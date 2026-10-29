# Standalone member packages

Each folder is one member's part of the project as a **self-contained, runnable package**: copy the folder to any laptop,
create a virtual environment, `pip install -r requirements.txt`, run the numbered scripts. No package imports from the parent
repository or needs another member's service.

| Folder | Member | Workstream | What runs | Tests |
|---|---|---|---|---|
| [`charles/`](charles/README.md) | Charles Jehanabad (24BIT0522) | A — prediction & data | 336 real RIPE Atlas raw files + 53 BIDMC files, checksum verification, rebuild of clean data and windows, trained LSTM (inference-only by default, `--train` to retrain), evaluation vs baselines, Streamlit dashboard with a clickable measurement→probe→network graph | 25 + 1 skipped without TensorFlow |
| [`tanmay/`](tanmay/README.md) | Tanmay Kapoor (24BIT0079) | B — decision engine | AHP weights and consistency, vetoes, explanations, multi-cloud ranking, 127 pipeline decisions reproduced, Streamlit dashboard with a clickable decision-flow graph | 184 |
| [`rani/`](rani/README.md) | Rani Gupta (24BIT0543) | C/D — execution, security, backend, database, alerts | FastAPI backend + SQLite (or PostgreSQL) with migrations, demo users, execution with retry/fallback, audit chain + tamper demo, mock-labelled alerts, persistence across restart, React portal and a Streamlit operations dashboard with a clickable request-flow graph | 69 |

Verification of each package (copied outside the repository, fresh virtual environment, Python 3.13): see
`charles/TEST_REPORT.md`, `tanmay/TEST_REPORT.md`, `rani/TEST_REPORT.md`; raw logs in `../results/tests/standalone/`.

## How the copies stay correct
Shared code is **not** rewritten for the packages. `export.py` copies the authoritative files from the main repository
byte-for-byte and records each SHA-256 in the package's `EXPORTED_FILES.json`:

```bash
python standalone_demos/export.py           # refresh all three packages after changing code in the main repo
python standalone_demos/export.py --check   # exit 1 if any copy differs (also run by tests/unit/test_standalone_sync.py)
```
Only the numbered scripts, `demo_common.py`, package tests, READMEs, requirements and `.env.example` are package-specific.
Edit shared code in the main repository, never inside a package.

## Relation to the integrated project
The integrated system (repository root) runs all three parts together: one API, one database, one React portal
(`frontend/`) with a **Project tour** page that presents the whole framework. The packages exist so that each member can
demonstrate and explain their own part independently. Mapping of every file to an owner: `docs/FILE_OWNERSHIP_MATRIX.md`;
workstreams A–E: `docs/WORKSTREAM_MAPPING.md`.
