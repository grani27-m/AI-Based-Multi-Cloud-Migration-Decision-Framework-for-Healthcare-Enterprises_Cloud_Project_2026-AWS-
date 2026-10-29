# AWS deployment report

**Status: nothing is deployed.** No AWS credentials or Learner Lab session were available while this version was built, and this
report does not claim otherwise. The current, machine-readable status shown on the dashboard's *System* page is
`infra/aws/service_status.json`.

## Chosen minimal architecture (report §7, reduced to what the project needs)
| Service | Why it is in the minimal set | Defined in | Local stand-in in use today |
|---|---|---|---|
| Amazon S3 | model artifacts + processed CLOUD-path objects | `infra/aws/template.yaml` `DataBucket` (SSE, public access blocked, versioning, IA after 30 days) | `local-cloud-object-store` (same key layout); `CLOUD_ADAPTER=s3` switches to real S3 |
| AWS Lambda + HTTP API | the AHP decision engine as a serverless function (report: "AHP routing function → Lambda") | `DecisionFunction` (python3.12, 256 MB, no layers) | same `decide()` inside FastAPI; handler unit-tested locally |
| Amazon SNS | emergency alert fan-out | `AlertTopic` (+ optional e-mail subscription) | Telegram / SMTP / webhook channels; `SNS_TOPIC_ARN` enables the SNS channel |
| Amazon CloudWatch | Lambda logs (30-day retention) + error alarm → SNS | `DecisionLogs`, `DecisionErrorAlarm` | structured logs + Prometheus `/metrics` |
| IAM | least-privilege Lambda role, or Learner Lab `LabRole` | `DecisionRole` / `ExistingRoleArn` | app-level JWT roles |

Deliberately **not** deployed (and why): SageMaker (numpy inference takes ~1 ms; an always-on endpoint is the main cost risk named in
the report), IoT Core/Greengrass (no physical devices), DynamoDB (relational schema with FKs and migrations already in PostgreSQL),
Cognito (JWT users table is sufficient for the prototype), QuickSight (React dashboard exists).

## How to deploy (your account; never paste credentials into chat or Git)
```bash
# prerequisites: AWS CLI v2 + AWS SAM CLI, credentials configured (aws configure, or Learner Lab "AWS Details")
export AWS_REGION=ap-south-1                     # Learner Lab usually requires us-east-1
EXISTING_ROLE_ARN=arn:aws:iam::<account>:role/LabRole  ALERT_EMAIL=you@example.com  bash infra/aws/deploy.sh
```
`deploy.sh` packages `src/decision` + the handler, runs `sam deploy`, stores the stack outputs, calls the deployed `/decide`
endpoint with the two report use cases (emergency → EDGE, routine → CLOUD), uploads the model artifacts to S3 and writes all of
this (account ID redacted) to `results/aws/`. Then set in `.env`: `CLOUD_ADAPTER=s3`, `S3_BUCKET=<output>`,
`SNS_TOPIC_ARN=<output>` (`pip install boto3`), restart the API and stream a few events; CLOUD executions will show
`adapter=aws-s3` and an `s3://` output reference. Update `service_status.json` with the evidence.

**Teardown:** `bash infra/aws/teardown.sh` (empties the versioned bucket and deletes the stack).

## Cost
Lambda/API/SNS/CloudWatch at demo volume stay inside the free tier; S3 < 1 GB. Expected < USD 1 for a demonstration (planning
estimate, not a bill). Set an AWS Budget alarm before deploying.
