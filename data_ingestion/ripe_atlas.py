"""
data_ingestion/ripe_atlas.py  —  Owner: Charles (24BIT0522)
================================================================
Reproducible downloader for REAL RIPE Atlas ping measurements.

Sub-commands
------------
  discover   Save metadata of the selected measurements and probes
             (dataset/metadata/ripe_atlas_measurements.json, ripe_atlas_probes.json).
  download   Download raw results for every (measurement, probe, week) chunk in
             dataset/config/ripe_atlas_selection.json. Raw API responses are saved
             gzipped and NEVER overwritten (existing chunks are skipped). A manifest
             with URL, retrieval time, SHA-256 and row count is appended for every chunk.
  verify     Re-hash every raw chunk and compare with the manifest.

Usage
-----
  python -m data_ingestion.ripe_atlas discover
  python -m data_ingestion.ripe_atlas download --workers 8
  python -m data_ingestion.ripe_atlas verify

The RIPE Atlas results endpoint is public for public measurements; no API key is
needed for reading. If RIPE_API_KEY is set it is sent as "Authorization: Key ...".
Data licence: RIPE Atlas data is provided under the RIPE NCC Terms and Conditions
(https://www.ripe.net/manage-ips-and-asns/legal/ripe-atlas-terms-and-conditions).
Parsing/cleaning lives in src/prediction/ripe_parser.py.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "dataset" / "config" / "ripe_atlas_selection.json"
RAW_DIR = ROOT / "dataset" / "raw" / "ripe_atlas"
META_DIR = ROOT / "dataset" / "metadata"
MANIFEST = META_DIR / "ripe_atlas_raw_manifest.jsonl"

log = logging.getLogger("ripe_atlas")
_manifest_lock = threading.Lock()


@dataclass(frozen=True)
class Chunk:
    msm_id: int
    probe_id: int
    start: int  # unix seconds, inclusive
    stop: int   # unix seconds, exclusive

    @property
    def path(self) -> Path:
        return RAW_DIR / f"msm{self.msm_id}" / f"probe{self.probe_id}" / f"{self.start}_{self.stop}.json.gz"

    def url(self, base: str) -> str:
        return (f"{base}/measurements/{self.msm_id}/results/"
                f"?start={self.start}&stop={self.stop - 1}&probe_ids={self.probe_id}&format=json")


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _iso_to_unix(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def plan_chunks(cfg: dict) -> list[Chunk]:
    start = _iso_to_unix(cfg["time_range_utc"]["start"])
    stop = _iso_to_unix(cfg["time_range_utc"]["stop"])
    step = int(cfg.get("chunk_days", 7)) * 86400
    probes = [p for group in cfg["probes"].values() for p in group]
    chunks = []
    for m in cfg["measurements"]:
        for p in probes:
            t = start
            while t < stop:
                chunks.append(Chunk(int(m["msm_id"]), int(p), t, min(t + step, stop)))
                t += step
    return chunks


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "healthcare-cloud-framework/1.0 (VIT BCSE355L student project)"
    key = os.environ.get("RIPE_API_KEY", "").strip()
    if key:
        s.headers["Authorization"] = f"Key {key}"
    return s


def fetch_json(session: requests.Session, url: str, retries: int = 5, timeout: int = 300):
    """GET with exponential back-off on timeouts, 429 and 5xx. Raises after the last retry."""
    delay = 5.0
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == retries:
                raise
            log.warning("attempt %d/%d failed for %s: %s; retrying in %.0fs", attempt, retries, url, exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 120)


def _append_manifest(entry: dict) -> None:
    META_DIR.mkdir(parents=True, exist_ok=True)
    with _manifest_lock, MANIFEST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def download_chunk(chunk: Chunk, base: str) -> dict:
    if chunk.path.exists():
        return {"chunk": chunk.path.name, "status": "skipped_exists"}
    session = _session()
    url = chunk.url(base)
    t0 = time.time()
    data = fetch_json(session, url)
    if not isinstance(data, list):
        raise ValueError(f"unexpected response type {type(data).__name__} for {url}")
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    chunk.path.parent.mkdir(parents=True, exist_ok=True)
    tmp = chunk.path.with_suffix(".tmp")
    with gzip.open(tmp, "wb") as f:
        f.write(raw)
    tmp.rename(chunk.path)  # atomic: a half-written file never looks complete
    entry = {
        "file": str(chunk.path.relative_to(ROOT)),
        "url": url,
        "msm_id": chunk.msm_id,
        "probe_id": chunk.probe_id,
        "start": chunk.start,
        "stop": chunk.stop,
        "rows": len(data),
        "sha256_uncompressed": hashlib.sha256(raw).hexdigest(),
        "sha256_file": hashlib.sha256(chunk.path.read_bytes()).hexdigest(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": round(time.time() - t0, 1),
    }
    _append_manifest(entry)
    return {"chunk": chunk.path.name, "status": "downloaded", "rows": len(data)}


def cmd_download(workers: int) -> int:
    cfg = load_config()
    chunks = plan_chunks(cfg)
    todo = [c for c in chunks if not c.path.exists()]
    log.info("%d chunks planned, %d already present, %d to download", len(chunks), len(chunks) - len(todo), len(todo))
    failures = 0
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(download_chunk, c, cfg["api_base"]): c for c in todo}
        for fut in as_completed(futs):
            c = futs[fut]
            done += 1
            try:
                res = fut.result()
                log.info("[%d/%d] msm%d probe%d %s rows=%s", done, len(todo), c.msm_id, c.probe_id,
                         res["status"], res.get("rows"))
            except Exception as exc:  # recorded, not swallowed: rerun download to retry
                failures += 1
                log.error("[%d/%d] FAILED msm%d probe%d %d-%d: %s", done, len(todo), c.msm_id, c.probe_id,
                          c.start, c.stop, exc)
    log.info("finished: %d failures (rerun the same command to retry only the missing chunks)", failures)
    return 1 if failures else 0


def cmd_discover() -> int:
    cfg = load_config()
    session = _session()
    META_DIR.mkdir(parents=True, exist_ok=True)
    msms = []
    for m in cfg["measurements"]:
        meta = fetch_json(session, f"{cfg['api_base']}/measurements/{m['msm_id']}/")
        msms.append({k: meta.get(k) for k in ("id", "type", "af", "target", "target_ip", "interval",
                                              "start_time", "stop_time", "status", "is_public", "description")})
    for c in cfg.get("rejected_candidates", []):
        if isinstance(c["msm_id"], int):
            meta = fetch_json(session, f"{cfg['api_base']}/measurements/{c['msm_id']}/")
            msms.append({"rejected": True, "reason": c["reason"],
                         **{k: meta.get(k) for k in ("id", "type", "target", "interval", "start_time",
                                                     "stop_time", "participant_count", "status")}})
    probes = []
    for group, ids in cfg["probes"].items():
        for pid in ids:
            p = fetch_json(session, f"{cfg['api_base']}/probes/{pid}/")
            probes.append({"group": group, **{k: p.get(k) for k in (
                "id", "country_code", "asn_v4", "description", "is_anchor", "is_public",
                "status", "first_connected", "total_uptime")}})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (META_DIR / "ripe_atlas_measurements.json").write_text(
        json.dumps({"retrieved_at": now, "measurements": msms}, indent=2), encoding="utf-8")
    (META_DIR / "ripe_atlas_probes.json").write_text(
        json.dumps({"retrieved_at": now, "probes": probes}, indent=2), encoding="utf-8")
    log.info("saved metadata for %d measurements and %d probes", len(msms), len(probes))
    return 0


def cmd_verify() -> int:
    if not MANIFEST.exists():
        log.error("no manifest at %s", MANIFEST)
        return 1
    bad = 0
    seen = 0
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        p = ROOT / e["file"]
        seen += 1
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != e["sha256_file"]:
            bad += 1
            log.error("checksum mismatch or missing: %s", e["file"])
    log.info("verified %d chunks, %d problems", seen, bad)
    return 1 if bad else 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    d = sub.add_parser("download")
    d.add_argument("--workers", type=int, default=6)
    sub.add_parser("verify")
    a = ap.parse_args(argv)
    if a.cmd == "discover":
        return cmd_discover()
    if a.cmd == "download":
        return cmd_download(a.workers)
    return cmd_verify()


if __name__ == "__main__":
    raise SystemExit(main())
