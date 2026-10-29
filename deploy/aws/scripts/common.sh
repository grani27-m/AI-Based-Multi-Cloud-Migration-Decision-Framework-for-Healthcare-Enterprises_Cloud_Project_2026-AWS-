#!/bin/bash
# shellcheck disable=SC2034  # variables are used by the scripts that source this file
# Sourced by the numbered scripts. Run them in AWS CloudShell (region eu-north-1), signed in as your hcf-deployers user.
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="hcf-app-${ACCOUNT_ID}-eu-north-1"
STACK=hcf-app
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
instance_id() { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text; }
run_on_instance() {  # run_on_instance "<shell commands>"  -> prints stdout/stderr of the command on the server
  local iid cid status
  iid=$(instance_id)
  cid=$(aws ssm send-command --instance-ids "$iid" --document-name AWS-RunShellScript --comment "hcf: ${2:-command}" \
        --parameters "$(python3 -c 'import json,sys;print(json.dumps({"commands":[sys.argv[1]],"executionTimeout":["1800"]}))' "$1")" \
        --query Command.CommandId --output text)
  echo "SSM command $cid on $iid ..."
  while true; do
    sleep 5
    status=$(aws ssm get-command-invocation --command-id "$cid" --instance-id "$iid" --query Status --output text 2>/dev/null || echo Pending)
    case $status in Pending|InProgress|Delayed) ;; *) break;; esac
  done
  aws ssm get-command-invocation --command-id "$cid" --instance-id "$iid" --query StandardOutputContent --output text
  local err; err=$(aws ssm get-command-invocation --command-id "$cid" --instance-id "$iid" --query StandardErrorContent --output text)
  [ -n "$err" ] && [ "$err" != "None" ] && echo "--- stderr ---" && echo "$err"
  echo "status: $status"
  [ "$status" = "Success" ]
}
