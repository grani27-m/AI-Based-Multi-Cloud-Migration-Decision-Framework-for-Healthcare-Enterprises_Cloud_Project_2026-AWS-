#!/bin/bash
# STAGE 0 - READ-ONLY checks. Creates nothing, costs nothing.   bash deploy/aws/scripts/00_preflight.sh
source "$(dirname "$0")/common.sh"
echo "== identity (must be your IAM user, NOT root)";  aws sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output table
case "$(aws sts get-caller-identity --query Arn --output text)" in *":root") echo "!! You are signed in as ROOT. Stop and sign in as the hcf deployer user."; exit 1;; esac
echo "== region: $AWS_REGION"
echo "== default VPC";   aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[].{VpcId:VpcId,Cidr:CidrBlock}' --output table
echo "== default subnets"; aws ec2 describe-subnets --filters Name=default-for-az,Values=true --query 'Subnets[].{AZ:AvailabilityZone,Subnet:SubnetId,PublicIp:MapPublicIpOnLaunch}' --output table
echo "== instance types offered here and free-tier flag"
aws ec2 describe-instance-types --instance-types t3.micro t3.small --query 'InstanceTypes[].{Type:InstanceType,FreeTierEligible:FreeTierEligible,MemoryMiB:MemoryInfo.SizeInMiB,vCPU:VCpuInfo.DefaultVCpus}' --output table
echo "== latest Amazon Linux 2023 AMI"; aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query 'Parameters[0].Value' --output text
echo "== existing hcf stacks"; aws cloudformation describe-stacks --query "Stacks[?starts_with(StackName,'hcf')].{Name:StackName,Status:StackStatus}" --output table 2>/dev/null || true
echo "== bootstrap export (instance profile)"; aws cloudformation list-exports --query "Exports[?Name=='hcf-ec2-profile-name'].Value" --output text
echo "== app bucket $BUCKET"; aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null && echo "exists" || echo "does not exist yet (created in stage 3)"
echo "== secrets present under /hcf/prod (names only)"; aws ssm get-parameters-by-path --path /hcf/prod --query 'Parameters[].Name' --output text || true
echo "== your public IP as seen from CloudShell is NOT your laptop's IP; on your laptop open https://checkip.amazonaws.com"
echo "== tools"; aws --version; python3 --version; git --version
echo "PREFLIGHT DONE (read-only)."
