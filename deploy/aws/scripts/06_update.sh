#!/bin/bash
# Roll out a new release: upload it, then rebuild/restart on the server. Data in PostgreSQL is kept.
source "$(dirname "$0")/common.sh"
bash "$(dirname "$0")/03_upload_release.sh"
run_on_instance "/usr/local/bin/hcf-update" update
