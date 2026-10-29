#!/bin/bash
# Delete EVERYTHING billable created for hcf-app: the stack (EC2, EBS, security group, SNS topic, log group, alarms),
# the bucket (releases, objects, backups) and the /hcf/prod secrets. Irreversible. The hcf-bootstrap stack (IAM + budget,
# no cost) is left for the account administrator to delete.
source "$(dirname "$0")/common.sh"
read -r -p "Type DELETE to remove stack $STACK, bucket $BUCKET and /hcf/prod secrets: " ok
[ "$ok" = "DELETE" ] || { echo "aborted"; exit 1; }
aws cloudformation delete-stack --stack-name "$STACK"
aws cloudformation wait stack-delete-complete --stack-name "$STACK" && echo "stack deleted"
aws s3 rm "s3://$BUCKET" --recursive && aws s3api delete-bucket --bucket "$BUCKET" && echo "bucket deleted"
for n in SECRET_KEY POSTGRES_PASSWORD ADMIN_PASSWORD DEVICE_PASSWORD; do aws ssm delete-parameter --name "/hcf/prod/$n" 2>/dev/null && echo "deleted /hcf/prod/$n"; done
echo "== remaining hcf resources (should be empty)"
aws cloudformation describe-stacks --query "Stacks[?StackName=='$STACK'].StackStatus" --output text
aws ec2 describe-instances --filters Name=tag:Project,Values=hcf Name=instance-state-name,Values=pending,running,stopped --query 'Reservations[].Instances[].InstanceId' --output text
