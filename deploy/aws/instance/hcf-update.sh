#!/bin/bash
# Runs ON the EC2 instance (as root, via user-data or `aws ssm send-command`). Never run it on your laptop.
#   hcf-update                 download releases/current.tar.gz from S3, rebuild, restart, wait for /ready
#   hcf-update --no-download   use the bundle already in /opt/hcf (first boot)
# Secrets come from SSM Parameter Store (/hcf/prod/*) and are written only to /opt/hcf/.env (mode 600, root).
set -euo pipefail
source /etc/hcf.conf
cd /opt/hcf
if [ "${1:-}" != "--no-download" ]; then
  aws s3 cp "s3://$HCF_BUCKET/$HCF_RELEASE_KEY" /tmp/hcf-release.tar.gz --region "$HCF_REGION"
  find /opt/hcf -mindepth 1 -maxdepth 1 ! -name .env -exec rm -rf {} +
  tar -xzf /tmp/hcf-release.tar.gz -C /opt/hcf
fi
p() { aws ssm get-parameter --region "$HCF_REGION" --name "/hcf/prod/$1" --with-decryption --query Parameter.Value --output text; }
umask 077
cat > /opt/hcf/.env <<ENV
ENVIRONMENT=production
SECRET_KEY=$(p SECRET_KEY)
POSTGRES_PASSWORD=$(p POSTGRES_PASSWORD)
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=$(p ADMIN_PASSWORD)
DEVICE_PASSWORD=$(p DEVICE_PASSWORD)
STREAM_USER=sim-device
CLOUD_ADAPTER=s3
S3_BUCKET=$HCF_BUCKET
AWS_DEFAULT_REGION=$HCF_REGION
SNS_TOPIC_ARN=$HCF_SNS_TOPIC_ARN
ALERT_NOTIFY_SEVERITIES=CRITICAL
RATE_LIMIT_PER_MINUTE=600
CORS_ORIGINS=
HCF_LOG_GROUP=$HCF_LOG_GROUP
ENV
chmod 600 /opt/hcf/.env
export HCF_LOG_GROUP HCF_REGION
docker compose -f deploy/aws/docker-compose.prod.yml --env-file .env up -d --build --remove-orphans
for _ in $(seq 1 60); do
  if curl -fs http://127.0.0.1/ready >/dev/null; then echo "hcf: ready"; curl -s http://127.0.0.1/ready; echo; exit 0; fi
  sleep 5
done
echo "hcf: API did not become ready" >&2
docker compose -f deploy/aws/docker-compose.prod.yml logs --tail 80 >&2 || true
exit 1
