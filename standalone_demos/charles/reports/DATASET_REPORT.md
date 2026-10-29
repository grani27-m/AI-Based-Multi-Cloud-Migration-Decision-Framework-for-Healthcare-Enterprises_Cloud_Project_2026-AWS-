# Dataset report

All counts below are produced by the pipeline (`dataset/metadata/*.json`), not typed by hand.
Rebuild everything with:

```bash
python -m data_ingestion.ripe_atlas discover      # measurement + probe metadata
python -m data_ingestion.ripe_atlas download --workers 8
python -m data_ingestion.ripe_atlas verify        # re-hash every raw chunk against the manifest
python -m data_ingestion.physionet_bidmc download # checks PhysioNet SHA256SUMS
python -m data_ingestion.physionet_bidmc build
python -m src.prediction.dataset build            # clean table + chronological windows
```

## 1. RIPE Atlas ping measurements — network-latency training data (mandatory, real)

| Attribute | Value |
|---|---|
| Source | RIPE NCC, RIPE Atlas REST API v2 — `https://atlas.ripe.net/api/v2/measurements/<id>/results/` |
| Licence / terms | RIPE Atlas public measurement data, RIPE NCC Terms & Conditions; cite RIPE NCC Staff (2015), *Internet Protocol Journal* 18(3) |
| Measurements | **1001** (ping k.root-servers.net 193.0.14.129) and **1004** (ping f.root-servers.net 192.5.5.241), built-in, IPv4, every 240 s, ongoing since 2010 |
| Probes | 20 public probes in India with data (21 selected; probe 1001134 returned no results for these measurements). 14 access-network probes (Airtel, BSNL, ACT, Hathway, Excitel, home networks) and 6 data-centre probes (AWS Mumbai AS16509, Oracle Mumbai/Hyderabad AS31898, E2E Noida, OVH) |
| Selection rule | public, connected on 2026-10-29, IPv4 ASN, highest total uptime; documented in `dataset/config/ripe_atlas_selection.json` |
| Period | 2026-09-02 00:00 → 2026-10-28 00:00 UTC (8 weeks), downloaded 2026-10-29 |
| Raw storage | 336 gzip JSON chunks (measurement × probe × week), 30 MB, `dataset/raw/ripe_atlas/` — never overwritten |
| Integrity | `dataset/metadata/ripe_atlas_raw_manifest.jsonl`: URL, retrieval time, row count, SHA-256 per chunk; `verify` → 336/336 OK |
| Rejected candidate | msm **228839605** (seen in the chat screenshot): checked through the API — 1 probe, a 2-day campaign (2026-10-28 → 10-30); far too short for a 20-step forecaster |

### Fields and provenance
| Column | Origin |
|---|---|
| `timestamp`, `msm_id`, `prb_id`, `sent`, `rcvd`, `rtt_min_ms`, `rtt_avg_ms`, `rtt_max_ms` | **observed** by RIPE Atlas |
| `loss_pct` = 100·(sent − rcvd)/sent | **derived** |
| `jitter_ms` = mean \|rtt_k − rtt_{k−1}\| over consecutive replies of one round (IPDV-style) | **derived** |
| `hour_sin`, `hour_cos` (UTC hour of day) | **derived** from timestamp |
| bandwidth, signal strength | **not available — not used.** The original downloader computed both from RTT with made-up formulas; they carried no independent information and were removed. |

### Cleaning (counts from `ripe_atlas_quality.json`)
| Step | Rows |
|---|---|
| Raw results downloaded | **756,495** |
| Invalid: `sent = 0` / inconsistent counts | −3,085 |
| Invalid RTT (≤0, ≥5000 ms, min>avg>max) | 0 |
| Duplicates (msm, probe, timestamp) | 0 |
| **Clean rows** | **753,410** |
| of which 100 % packet loss (kept; RTT carried forward, loss = 100 tells the model) | 43,412 |
| RTT ≥ 150 ms | 573 |
| RTT ≥ 300 ms (network-veto threshold) | **47** |
| Series (probe × measurement) / contiguous segments (gap > 360 s splits a series) | 40 / 710 |
| RTT distribution | median 15.2 ms, p95 87.0 ms, p99 126.4 ms, max 1030 ms |

Outliers are **not** removed: spikes are exactly what the model must anticipate.

### Windows and splits (`ripe_atlas_splits.json`)
Window = 20 consecutive rounds (~80 min) → target = `rtt_avg_ms` of the next round (240 s ahead).
Global chronological cut-offs, identical for every probe; a window belongs to a split only if all 21 timestamps fall inside it:

| Split | Period (UTC) | Windows |
|---|---|---|
| Train | 2026-09-02 → 2026-10-11 04:47 | 475,196 |
| Validation | 2026-10-11 04:47 → 2026-10-19 14:23 | 111,314 |
| Test (held out) | 2026-10-19 14:23 → 2026-10-27 23:59 | 113,077 |

Windows whose target round had 100 % loss (no RTT to predict) and windows straddling a split boundary or a gap are dropped.
The scaler is fitted on training windows only.

**About the old figure "2,830,022 measurements / 201 MB":** no file, script or log in the repository supports it, so it is
not used. The verified number for this project is 756,495 raw results / 753,410 clean rows.

## 2. PhysioNet BIDMC PPG and Respiration Dataset v1.0.0 — real vital signs (report §6 "planned source")

| Attribute | Value |
|---|---|
| Source | https://physionet.org/content/bidmc/1.0.0/ (open access) |
| Licence | Open Data Commons Attribution License v1.0; cite Pimentel et al., IEEE TBME 64(8), 2016 and Goldberger et al., Circulation 2000 |
| Files | 53 `bidmc_XX_Numerics.csv` (HR, PULSE, RESP, SpO₂ at 1 Hz, 8 min per adult ICU stay) |
| Integrity | every file matches PhysioNet's `SHA256SUMS.txt` (53/53) — `dataset/metadata/physionet_bidmc_manifest.json` |
| Rows | 25,493 raw → 25,485 clean (out-of-range values set to NaN and forward-filled within the record: HR 4, PULSE 128, RESP 375, SpO₂ 128; 8 rows unrecoverable) |
| Use | patient-criticality criterion only (partial NEWS2, `src/decision/criticality.py`). **Never mixed into the network model.** |
| Privacy | de-identified source; only HR/RESP/SpO₂ numbers are used; age/sex headers are not downloaded |

## 3. Simulated IoMT stream (labelled synthetic)
`data_ingestion/simulator.py`, `source="simulated"`, seeded and reproducible; scenarios normal / degraded / emergency / failure / mixed.
Used for controlled demonstrations of rare situations (e.g. RTT ≥ 300 ms) and for load testing. Never used for training.

## 4. Replay stream (real data, artificial pairing)
`data_ingestion/replay.py`, `source="replay"`: a 20-round window from the **held-out test period** of one RIPE series plus one
second of a BIDMC record. The pairing of network path and patient is artificial and the cloud-cost index is a synthetic
time-of-day proxy; both facts are written into every event's `provenance`. Event IDs are deterministic, so replaying the same
seed is idempotent.

## 5. Not in scope
PTB-XL / MIT-BIH ECG datasets were discussed in chat but the project report has no ECG-classification objective; they were not
added. Nothing in the system claims ECG diagnosis.

## 6. What is committed to Git
* raw RIPE chunks (30 MB) + manifest, BIDMC numerics (CSV), cleaned table `dataset/processed/ripe_atlas_clean.csv.gz` (18 MB),
  metadata/quality/splits JSON, replay samples in `dataset/samples/`;
* not committed (regenerated in ~20 s): `dataset/processed/windows_w20.npz`.
