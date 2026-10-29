#!/bin/bash
# Runs ON the EC2 instance daily (cron 02:17 UTC): pg_dump -> gzip -> s3://<bucket>/backups/ (expires after 14 days).
set -euo pipefail
source /etc/hcf.conf
cd /opt/hcf
f="/tmp/hcf-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose -f deploy/aws/docker-compose.prod.yml exec -T postgres pg_dump -U hcf -d hcf | gzip > "$f"
aws s3 cp "$f" "s3://$HCF_BUCKET/backups/$(basename "$f")" --region "$HCF_REGION"
rm -f "$f"
echo "backup uploaded: backups/$(basename "$f")"
