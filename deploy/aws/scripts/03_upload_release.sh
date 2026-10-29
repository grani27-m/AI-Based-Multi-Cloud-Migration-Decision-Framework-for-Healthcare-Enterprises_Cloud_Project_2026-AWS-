#!/bin/bash
# STAGE 3c - package the application (code + trained model + small metadata + prebuilt dashboard; NO raw datasets)
# and upload it to s3://<bucket>/releases/current.tar.gz. Run from a checkout/unzip of the repository in CloudShell.
source "$(dirname "$0")/common.sh"
cd "$REPO_ROOT" || exit 1
[ -f frontend/dist/index.html ] || { mkdir -p frontend/dist; cp -r standalone_demos/rani/frontend/dist/. frontend/dist/; echo "using prebuilt dashboard from standalone_demos/rani/frontend/dist"; }
VERSION=$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)
OUT=/tmp/hcf-release-$VERSION.tar.gz
tar --exclude='__pycache__' --exclude='*.pyc' -czf "$OUT" requirements.txt alembic.ini backend src data_ingestion scripts migrations models results/model/metrics.json \
  results/model/*.png dataset/config dataset/metadata dataset/samples infra/aws/service_status.json frontend/dist deploy/aws
ls -lh "$OUT"
tar -tzf "$OUT" | grep -E '^dataset/raw|\.env$' && { echo "!! release contains raw data or a .env - aborting"; exit 1; } || true
aws s3 cp "$OUT" "s3://$BUCKET/releases/archive/hcf-release-$VERSION.tar.gz"
aws s3 cp "$OUT" "s3://$BUCKET/releases/current.tar.gz"
echo "uploaded release $VERSION"; aws s3 ls "s3://$BUCKET/releases/" --recursive --human-readable
