#!/bin/bash
# STAGE 3b - generate random secrets ON AWS (SSM Parameter Store SecureString, standard tier = no charge).
# Nothing is printed or written to disk. Existing values are kept unless you pass --rotate.
source "$(dirname "$0")/common.sh"
put() {
  local name=/hcf/prod/$1
  if [ "${ROTATE:-0}" = 0 ] && aws ssm get-parameter --name "$name" >/dev/null 2>&1; then echo "kept    $name"; return; fi
  aws ssm put-parameter --name "$name" --type SecureString --overwrite --value "$(python3 -c "import secrets;print(secrets.token_urlsafe($2))")" >/dev/null
  echo "set     $name"
}
[ "${1:-}" = "--rotate" ] && ROTATE=1
put SECRET_KEY 48; put POSTGRES_PASSWORD 24; put ADMIN_PASSWORD 18; put DEVICE_PASSWORD 18
echo "Read the admin password when you need it (shown only in your own CloudShell):"
echo "  aws ssm get-parameter --name /hcf/prod/ADMIN_PASSWORD --with-decryption --query Parameter.Value --output text"
