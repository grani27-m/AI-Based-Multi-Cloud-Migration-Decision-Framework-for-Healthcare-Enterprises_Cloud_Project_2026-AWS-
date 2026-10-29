#!/bin/bash
# STAGE 3a - create the private, encrypted app bucket (release bundles, CLOUD-path objects, DB backups). Billable: S3 storage
# (a few MB; cents per month). Safe to re-run.
source "$(dirname "$0")/common.sh"
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then echo "bucket $BUCKET already exists"; else
  aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint=eu-north-1 >/dev/null
  echo "created $BUCKET"; fi
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-ownership-controls --bucket "$BUCKET" --ownership-controls '{"Rules":[{"ObjectOwnership":"BucketOwnerEnforced"}]}'
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration '{"Rules":[
  {"ID":"expire-backups","Status":"Enabled","Filter":{"Prefix":"backups/"},"Expiration":{"Days":14}},
  {"ID":"expire-processed","Status":"Enabled","Filter":{"Prefix":"processed/"},"Expiration":{"Days":30}},
  {"ID":"expire-old-releases","Status":"Enabled","Filter":{"Prefix":"releases/archive/"},"Expiration":{"Days":30}}]}'
aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging 'TagSet=[{Key=Project,Value=hcf}]'
echo "== verify"; aws s3api get-public-access-block --bucket "$BUCKET" --output table; aws s3api get-bucket-encryption --bucket "$BUCKET" --query 'ServerSideEncryptionConfiguration.Rules[0]' --output table
