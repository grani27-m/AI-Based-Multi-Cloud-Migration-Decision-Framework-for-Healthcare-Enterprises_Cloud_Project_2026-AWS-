# Deploying the complete project on AWS (eu-north-1, Stockholm)

**Status: prepared and validated locally, NOT deployed.** Nothing in this repository has been run against your AWS account.
The deployment counts as done only after you have executed the stages below and the deployed application has passed
Stage 5. Work **one stage at a time** and send the output of each stage before starting the next.

---

## 1. Audit of the deployment configuration (what was there, what was fixed, what is needed)

| Item | Before this pass | Now |
|---|---|---|
| What gets deployed | `infra/aws/template.yaml` (SAM): only the AHP Lambda + S3 + SNS. The application itself (API, model, DB, dashboard) was not deployed anywhere | `deploy/aws/app.yaml`: the **whole integrated system** on one EC2 instance (API + LSTM + AHP + execution + React dashboard + PostgreSQL), plus S3, SNS, CloudWatch |
| Region | default `ap-south-1` | fixed to **eu-north-1** everywhere (templates, scripts, IAM conditions) |
| Credentials | `aws configure` with access keys, SAM CLI on a laptop | **no access keys at all**: you work in AWS CloudShell in the browser, signed in as a least-privilege IAM user with MFA; the server uses an instance role |
| IAM | none for humans; Lambda role only | `deploy/aws/bootstrap.yaml`: group `hcf-deployers` with a scoped policy (only `hcf-*` resources, only eu-north-1, **no IAM write**, can pass only the one server role) and server role `hcf-ec2-role` |
| Secrets | `.env` file you fill by hand | random values generated **on AWS** into SSM Parameter Store SecureStrings `/hcf/prod/*`; the server reads them at start; nothing in Git, chat or logs |
| Container build | root `Dockerfile` builds the React app with Node — too heavy for a 1 GiB server | `deploy/aws/Dockerfile.ec2` uses the prebuilt dashboard in the release bundle |
| AWS SDK | `boto3` missing from runtime requirements (S3 adapter / SNS channel would fail) | `deploy/aws/requirements-aws.txt` installed in the server image |
| Datasets in the image | `.dockerignore` already excluded raw data | release bundle is **1.5 MB**: code, trained model, metadata and the small replay sample only; the packaging script aborts if raw data or a `.env` slips in |
| Logs / monitoring | none on AWS | container logs → CloudWatch Logs `/hcf/prod` (14-day retention); alarms for failed status checks and high CPU → e-mail |
| Backups | none | daily `pg_dump` → `s3://…/backups/` (kept 14 days), plus `07_backup_now.sh` |
| Cost guard | none | AWS Budget e-mail at 80 % forecast / 100 % actual (`admin_create_budget.sh`) |
| dev / test / prod config | one `.env.example` | `config/env/{development,test,production}.env.example`; production values come only from SSM |

The old SAM template (`infra/aws/template.yaml`, decision engine as a Lambda) is kept as an optional extra and is not
part of this deployment.

**Validated locally (no AWS):** `cfn-lint` on both templates (0 findings), `shellcheck` on all scripts (0 warnings),
the release bundle built exactly as `03_upload_release.sh` does (1.5 MB, no raw data), the server image built from that
bundle with `Dockerfile.ec2`, the production compose file started with PostgreSQL, `/ready` = database + model loaded, and
the Stage-5 smoke code run inside the container (real replay event → LSTM → AHP → execution → PostgreSQL → audit chain
valid; memory 204 MiB API + 60 MiB PostgreSQL). `tests/unit/test_aws_deployment.py` (10 tests) checks the IAM policy has no
wildcards or IAM write, the server has no SSH and requires IMDSv2 with an encrypted disk, and exercises the S3 adapter and
SNS channel against botocore's Stubber. **Not validated:** anything that needs your account (CloudFormation execution,
real S3/SNS/CloudWatch calls, the user-data script on a real instance).

## 2. Architecture

```
your laptop (only your IP, port 80) ──HTTP──► EC2 t3.micro, Amazon Linux 2023, eu-north-1 (default VPC)
                                              ├─ Docker: api (FastAPI + LSTM + AHP + execution + React)  :80
                                              ├─ Docker: postgres 16 (data on the encrypted gp3 EBS volume)
                                              ├─ instance role hcf-ec2-role (no keys on disk)
                                              └─ cron: daily pg_dump
        S3  hcf-app-<account>-eu-north-1   releases/  processed/ (CLOUD-path execution output)  backups/
        SNS hcf-alerts ──► your e-mail     (emergency / execution-failure alerts and health alarms)
        CloudWatch Logs /hcf/prod + 2 alarms        SSM Parameter Store /hcf/prod/* (secrets)
        SSM Session Manager / Run Command (shell access without SSH; port 22 closed)
```

Why this and not more: one small VM is the cheapest way to run a stateful API + PostgreSQL + the model together. RDS,
a load balancer, NAT gateway, ECS/Fargate or SageMaker would each add a fixed monthly cost without changing what the
review sees (the LSTM runs in ~1 ms on the CPU). TLS needs a domain name; without one, the page is served over HTTP and
access is restricted to your IP — do not use real patient data.

## 3. Cost (estimate — confirm in the AWS Pricing Calculator; prices change)

| Resource | Rate (eu-north-1, on-demand) | Per month if left running | Notes |
|---|---|---|---|
| EC2 t3.micro | ≈ $0.0108 / hour | ≈ $7.9 | `FreeTierEligible` is shown by Stage 2; free-tier hours apply only if your account qualifies |
| (alternative) t3.small | ≈ $0.0216 / hour | ≈ $15.8 | only if t3.micro runs out of memory |
| EBS gp3 16 GiB | ≈ $0.0836 / GiB-month | ≈ $1.3 | deleted with the stack |
| Public IPv4 address | $0.005 / hour while attached | ≈ $3.7 | AWS free tier includes 750 h/month for eligible accounts; no charge while the instance is stopped |
| S3 (a few MB) | per GB-month + requests | < $0.05 | |
| SNS e-mail, CloudWatch (2 alarms, small logs), SSM Standard parameters, Session Manager, Budgets | | ≈ $0 – 0.5 | mostly within free allowances |
| **Total** | | **≈ $13 / month** (t3.micro) | a one-week demo ≈ $3; **stop** the instance between demos, **teardown** after the review |

## 4. Who does what (IAM)

| Identity | Used for | Permissions |
|---|---|---|
| **Root user** | Stage 1 only: check/enable root MFA, deploy `hcf-bootstrap`, create the budget and the deployer user. Then sign out and do not use it again for this project | everything (that is why it is not used day to day) |
| **IAM user `hcf-deployer`** (console password + MFA, **no access keys**) | Stages 2–6 in CloudShell | group `hcf-deployers`: CloudFormation only on stack `hcf-app`; EC2 only in eu-north-1; S3 only bucket `hcf-app-<account>-eu-north-1`; SNS only `hcf-*`; logs only `/hcf/*`; alarms only `hcf-*`; SSM parameters only `/hcf/*`; Run Command/Session Manager only on instances tagged `Project=hcf`; `iam:PassRole` only for `hcf-ec2-role` and only to EC2; **cannot create or change any IAM user, role or policy**; plus AWS CloudShell |
| **Role `hcf-ec2-role`** (the server) | runtime | read/write its bucket; read `/hcf/prod/*`; write logs to `/hcf/prod`; publish to `hcf-alerts`; SSM agent core policy |

You will never be asked for, and must never share: root password, MFA codes, access keys, session cookies, or the
generated application passwords. Send command **output** only; the scripts never print secrets (except where you
explicitly read your own admin password in your own CloudShell).

---

## 5. Stages

Each stage lists: **where** · **command** · **what it does** · **expected output** · **how to verify** · **if it fails** · **billable?**

### Stage 0 — read-only checks and local validation  (no cost, nothing is created)

**0A · your laptop, in the unzipped project folder** (Python venv with `pip install -r requirements-dev.txt`):
```bash
python -m pytest tests/unit/test_aws_deployment.py -q
```
*Does:* static checks of the templates/IAM policy and S3/SNS code against a stub (no AWS calls). *Expected:* `10 passed`.
*If it fails:* send the output.

**0B · AWS console, signed in as root, read-only look (do not change anything yet):**
1. Top-right region selector → **Europe (Stockholm) eu-north-1**.
2. *IAM → Dashboard → Security recommendations:* is **MFA enabled for the root user**? Are there **root access keys**? (Answer yes/no.)
3. *Billing and Cost Management → Free Tier* (or *Home*): does the page show free-tier usage / credits for this account? (Answer what it shows; no numbers from your card.)
4. Open **CloudShell** (the `>_` icon in the top bar) once and run, read-only:
   ```bash
   aws sts get-caller-identity --query Arn --output text | sed 's/[0-9]\{12\}/<account>/'
   aws ec2 describe-vpcs --region eu-north-1 --filters Name=is-default,Values=true --query 'Vpcs[].VpcId' --output text
   aws ec2 describe-instance-types --region eu-north-1 --instance-types t3.micro --query 'InstanceTypes[0].FreeTierEligible'
   ```
   *Expected:* `arn:aws:iam::<account>:root` · a `vpc-…` id · `true` or `false`.
   *If there is no default VPC:* say so — the template then needs a subnet parameter.

**Send me:** the 0A test summary line, the three yes/no answers from 0B, and the three CloudShell outputs. **Stop here.**

### Stage 1 — one-time account setup (root, then never again)  · not billable
Only after Stage 0 is reviewed. Detailed commands will be given then; in short:
1. Enable root MFA if it is off; delete root access keys if any exist.
2. CloudShell → *Actions → Upload file* → `hcf-aws-deploy-kit.zip`; `unzip -q hcf-aws-deploy-kit.zip -d hcf && cd hcf`.
3. `aws cloudformation deploy --region eu-north-1 --stack-name hcf-bootstrap --template-file deploy/aws/bootstrap.yaml --capabilities CAPABILITY_NAMED_IAM`
4. `bash deploy/aws/scripts/admin_create_budget.sh <your-email> 15`
5. IAM console → *Users → Create user* `hcf-deployer`, console access, **no access key**, add to group `hcf-deployers`; sign in as that user, assign MFA; sign out of root.

### Stage 2 — deployer pre-flight (read-only) · not billable
Signed in as `hcf-deployer`, CloudShell in eu-north-1, kit uploaded and unzipped: `bash deploy/aws/scripts/00_preflight.sh`

### Stage 3 — storage, secrets, release · billable only for a few MB of S3
`01_create_bucket.sh` → `02_set_secrets.sh` → `03_upload_release.sh`

### Stage 4 — create the server · **billable from here**
`bash deploy/aws/scripts/04_deploy_stack.sh <your-laptop-ip>/32 <alert-email>` (your IP from https://checkip.amazonaws.com on the laptop)
— takes ~10–15 minutes (instance boot, Docker install, image build). Confirm the SNS e-mail subscription.

### Stage 5 — test the deployed application
`bash deploy/aws/scripts/05_smoke_test.sh` (server-side checks via SSM), then from your laptop open the `DashboardUrl`,
sign in as `admin` (password: `aws ssm get-parameter --name /hcf/prod/ADMIN_PASSWORD --with-decryption --query Parameter.Value --output text`
in your CloudShell), run *Admin → Demo runner* (replay + an emergency scenario), check *Project tour*, *Request trace*
(execution adapter `aws-s3`, `s3://` output), the alert e-mail, and CloudWatch Logs `/hcf/prod`.

### Stage 6 — operate and clean up
`06_update.sh` (new release) · `07_backup_now.sh` · stop/start the instance in the EC2 console between demos (the public
IP changes after a stop) · **`99_teardown.sh`** after the review (asks you to type DELETE), then the account admin may
delete `hcf-bootstrap` and the budget.

## 6. Files
| File | Purpose |
|---|---|
| `deploy/aws/bootstrap.yaml` | one-time IAM setup (deployer group/policy, server role/profile) |
| `deploy/aws/app.yaml` | application stack (EC2, security group, SNS, log group, alarms) |
| `deploy/aws/scripts/00…07, 99, admin_create_budget.sh, common.sh` | the staged commands (CloudShell) |
| `deploy/aws/instance/hcf-update.sh`, `hcf-backup.sh` | run on the server (user-data, SSM Run Command, cron) |
| `deploy/aws/docker-compose.prod.yml`, `Dockerfile.ec2`, `requirements-aws.txt` | production containers |
| `deploy/aws/docker-compose.localcheck.yml` | run the production compose locally without AWS |
| `config/env/*.env.example` | development / test / production configuration keys |
| `tests/unit/test_aws_deployment.py` | offline checks of all of the above |
