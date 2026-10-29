#!/usr/bin/env bash
# Deploy the minimal AWS stack and record evidence. Run from the repository root on a machine with
# AWS credentials already configured (aws configure / Learner Lab credentials). Never commit credentials.
#   bash infra/aws/deploy.sh                      # creates its own least-privilege role
#   EXISTING_ROLE_ARN=arn:aws:iam::<acct>:role/LabRole bash infra/aws/deploy.sh   # Learner Lab
set -euo pipefail
STACK=${STACK:-hcf-routing}
REGION=${AWS_REGION:-ap-south-1}
EVID=results/aws
mkdir -p "$EVID" infra/aws/build
rm -rf infra/aws/build/*
mkdir -p infra/aws/build/src/decision infra/aws/build/infra/aws/lambda_decision
cp src/__init__.py infra/aws/build/src/ 2>/dev/null || touch infra/aws/build/src/__init__.py
cp src/decision/*.py infra/aws/build/src/decision/
touch infra/aws/build/infra/__init__.py infra/aws/build/infra/aws/__init__.py
cp infra/aws/lambda_decision/handler.py infra/aws/build/infra/aws/lambda_decision/
touch infra/aws/build/infra/aws/lambda_decision/__init__.py
aws sts get-caller-identity --query '{account:Account,arn:Arn}' --output json | sed 's/[0-9]\{12\}/<account>/g' > "$EVID/caller_identity_redacted.json"
sam deploy --template-file infra/aws/template.yaml --stack-name "$STACK" --region "$REGION" \
  --capabilities CAPABILITY_IAM --resolve-s3 --no-fail-on-empty-changeset \
  --parameter-overrides ExistingRoleArn="${EXISTING_ROLE_ARN:-}" AlertEmail="${ALERT_EMAIL:-}"
aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" --query 'Stacks[0].Outputs' > "$EVID/stack_outputs.json"
URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" --query "Stacks[0].Outputs[?OutputKey=='DecideUrl'].OutputValue" --output text)
BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" --output text)
echo "== smoke tests" | tee "$EVID/smoke_tests.txt"
curl -sS -X POST "$URL" -H 'Content-Type: application/json' -d '{"device_id":"ECG-101","criticality":9.5,"predicted_latency_ms":210.5,"cloud_cost_index":0.4}' | tee -a "$EVID/smoke_tests.txt"; echo | tee -a "$EVID/smoke_tests.txt"
curl -sS -X POST "$URL" -H 'Content-Type: application/json' -d '{"device_id":"ECG-102","criticality":0.9,"predicted_latency_ms":33.8,"cloud_cost_index":0.2}' | tee -a "$EVID/smoke_tests.txt"; echo | tee -a "$EVID/smoke_tests.txt"
aws s3 cp models/latency_lstm/weights.npz "s3://$BUCKET/models/latency_lstm/weights.npz"
aws s3 cp models/latency_lstm/preprocessing.json "s3://$BUCKET/models/latency_lstm/preprocessing.json"
aws s3 ls "s3://$BUCKET/models/latency_lstm/" | tee -a "$EVID/smoke_tests.txt"
echo "Deployed. To route CLOUD executions to S3 set CLOUD_ADAPTER=s3 S3_BUCKET=$BUCKET in .env."
echo "Now update infra/aws/service_status.json (status + evidence) for the services you verified."
