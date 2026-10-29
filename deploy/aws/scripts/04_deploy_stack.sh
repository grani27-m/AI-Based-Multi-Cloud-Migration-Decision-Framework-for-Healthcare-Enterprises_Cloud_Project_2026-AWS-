#!/bin/bash
# STAGE 4 - create/update the hcf-app stack. BILLABLE from here: EC2 instance + EBS + public IPv4 while it exists.
#   bash deploy/aws/scripts/04_deploy_stack.sh <your-ip>/32 <alert-email> [t3.micro|t3.small]
source "$(dirname "$0")/common.sh"
CIDR=${1:?usage: 04_deploy_stack.sh <your-laptop-ip>/32 <alert-email> [instance-type]}; EMAIL=${2:?alert e-mail}; TYPE=${3:-t3.micro}
aws cloudformation validate-template --template-body "file://$REPO_ROOT/deploy/aws/app.yaml" >/dev/null && echo "template valid"
aws cloudformation deploy --stack-name "$STACK" --template-file "$REPO_ROOT/deploy/aws/app.yaml" --no-fail-on-empty-changeset \
  --parameter-overrides "AllowedCidr=$CIDR" "AlertEmail=$EMAIL" "InstanceType=$TYPE" --tags Project=hcf
aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].Outputs' --output table
echo "Confirm the SNS subscription e-mail sent to $EMAIL, then run 05_smoke_test.sh"
