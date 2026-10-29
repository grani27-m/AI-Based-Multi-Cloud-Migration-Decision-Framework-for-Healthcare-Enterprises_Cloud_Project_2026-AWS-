# Archive — superseded material, kept for history

These files come from the repository as received (baseline commit `b825c85`). They contain claims that the audit could
**not** verify and that are contradicted by the current evidence, so they must not be quoted in the final report:

| File | Problem |
|---|---|
| `PROJECT_COMPLETION_REPORT.md` | "100 % complete", "99/99 tests passing", LSTM "trained" — no model file, data or test log existed |
| `dataset_description.md/.pdf` | "2,830,022 records, ~201 MB, 10,000+ probes"; bandwidth and signal strength described as RIPE features (they were fabricated from RTT) |
| `old_results/*` | images/spreadsheet with no script or data that produced them; dashboard figures (518 events, "32 alerts sent") from the prototype with the counting defects |

Current, verified equivalents: `reports/DATASET_REPORT.md`, `reports/MODEL_EVALUATION_REPORT.md`,
`reports/SECURITY_AND_TEST_REPORT.md`, `results/`.
| `AWS_Cloud_Project_Report.md`, `FINAL_REPORT_AND_SPEECH.md`, `PROJECT_SPEECH.md` | earlier report/speech drafts repeating the 2,830,022-record and 99-test claims |

**For the final report**, take numbers only from `reports/*.md` and `results/`. A list of the report sections that must change
is in `reports/FINAL_STATUS.md` §4.
