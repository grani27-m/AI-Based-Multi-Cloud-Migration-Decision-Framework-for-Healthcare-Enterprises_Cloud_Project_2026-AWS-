#!/bin/bash
# STAGE 5 - verify the deployment ON the server (via SSM; CloudShell cannot reach port 80 because only your IP is allowed):
# health, readiness (DB + model), login, one REAL replay event through the whole pipeline (LSTM -> AHP -> S3 execution ->
# PostgreSQL -> audit), audit-chain verification. Creates one event in the production database.
source "$(dirname "$0")/common.sh"
read -r -d '' CMD <<'REMOTE' || true
set -e
cd /opt/hcf
echo "== containers"; docker compose -f deploy/aws/docker-compose.prod.yml ps
echo "== /health"; curl -s http://127.0.0.1/health; echo
echo "== /ready";  curl -s http://127.0.0.1/ready; echo
docker compose -f deploy/aws/docker-compose.prod.yml exec -T api python - <<'PY'
import os, httpx
from data_ingestion.replay import build_replay_events
c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60)
tok = lambda u, p: {"Authorization": "Bearer " + c.post("/api/v1/auth/login", json={"username": u, "password": p}).raise_for_status().json()["access_token"]}
adm = tok("admin", os.environ["BOOTSTRAP_ADMIN_PASSWORD"])
users = {u["username"] for u in c.get("/api/v1/users", headers=adm).json()}
if "sim-device" not in users:
    c.post("/api/v1/users", headers=adm, json={"username": "sim-device", "full_name": "replay gateway", "role": "device", "password": os.environ["DEVICE_PASSWORD"]}).raise_for_status()
dev = tok("sim-device", os.environ["DEVICE_PASSWORD"])
ev = build_replay_events(1, seed=int.from_bytes(os.urandom(2), "big"))[0]
b = c.post("/api/v1/events", json=ev, headers=dev).raise_for_status().json()
print("== real replay event", b["event_id"])
print("   prediction:", b["prediction"]["method"], round(b["prediction"]["predicted_rtt_ms"], 2), "ms, model", b["prediction"]["model_version"])
print("   decision:  ", b["decision"]["destination"], b["decision"]["reason"])
print("   execution: ", b["execution"]["status"], b["execution"]["adapter"], b["execution"]["output_ref"])
v = c.get("/api/v1/audit/verify", headers=adm).json()
print("== audit chain valid:", v["valid"], "entries:", v["checked"])
info = c.get("/api/v1/system/info", headers=adm).json()
print("== database:", info["database"], " alert channels:", info["alert_channels_configured"])
PY
REMOTE
run_on_instance "$CMD" smoke-test
echo "== CLOUD-path objects in S3 (written by the aws-s3 execution adapter)"; aws s3 ls "s3://$BUCKET/processed/" --recursive | tail -n 5
echo "== latest container logs in CloudWatch"; aws logs describe-log-streams --log-group-name /hcf/prod --query 'logStreams[].logStreamName' --output text
