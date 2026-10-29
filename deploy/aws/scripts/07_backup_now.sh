#!/bin/bash
# Take a PostgreSQL backup now (also runs daily at 02:17 UTC) and list backups in S3.
source "$(dirname "$0")/common.sh"
run_on_instance "/usr/local/bin/hcf-backup" backup
aws s3 ls "s3://$BUCKET/backups/" --human-readable
