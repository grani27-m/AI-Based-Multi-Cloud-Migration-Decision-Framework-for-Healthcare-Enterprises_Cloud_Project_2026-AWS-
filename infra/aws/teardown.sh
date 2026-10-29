#!/usr/bin/env bash
# Delete every billable resource created by deploy.sh.
set -euo pipefail
STACK=${STACK:-hcf-routing}; REGION=${AWS_REGION:-ap-south-1}
BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" --query "Stacks[0].Outputs[?OutputKey=='DataBucketName'].OutputValue" --output text || true)
if [ -n "${BUCKET:-}" ] && [ "$BUCKET" != "None" ]; then
  aws s3api delete-objects --bucket "$BUCKET" --delete "$(aws s3api list-object-versions --bucket "$BUCKET" --output json --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}')" >/dev/null 2>&1 || true
  aws s3api delete-objects --bucket "$BUCKET" --delete "$(aws s3api list-object-versions --bucket "$BUCKET" --output json --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}')" >/dev/null 2>&1 || true
fi
sam delete --stack-name "$STACK" --region "$REGION" --no-prompts
echo "Stack $STACK deleted."
