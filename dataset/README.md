# dataset/
| Folder | Content | In Git |
|---|---|---|
| `config/ripe_atlas_selection.json` | which RIPE Atlas measurements/probes/period are used and why | yes |
| `raw/ripe_atlas/msm*/probe*/*.json.gz` | untouched API responses, one file per measurement × probe × week | yes (30 MB) |
| `raw/physionet_bidmc/` | 53 BIDMC numerics CSVs + licence | yes |
| `metadata/` | manifests with SHA-256, measurement/probe metadata, quality counts, splits | yes |
| `processed/ripe_atlas_clean.csv.gz` | one validated row per ping round | yes (18 MB) |
| `processed/windows_w20.npz`, `processed/bidmc_vitals_1hz.csv` | model windows / cleaned vitals | **no** — rebuild |
| `samples/` | small extracts used by the replay demo when the full rebuild is absent | yes |

Rebuild: see `reports/DATASET_REPORT.md` (one command per step). Licences: RIPE NCC Terms & Conditions; BIDMC ODC-By 1.0.
