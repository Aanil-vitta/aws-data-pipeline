# Serverless CSV ETL Pipeline on AWS

A fully serverless, event-driven data pipeline: drop a CSV into S3, and it's
automatically validated, transformed, and loaded into DynamoDB — with zero
servers to manage and zero idle cost.

Built to demonstrate Infrastructure as Code, event-driven serverless
architecture, CI/CD, and observability — the core skills for a Cloud/DevOps
role — while staying entirely within the AWS Free Tier.

## Architecture

```
   CSV file
      |
      v
 +-----------+        S3 PUT event        +--------------------+
 |  S3 bucket| -------------------------->  |  Lambda (Python)   |
 |  (raw/)   |                              |  parse + validate  |
 +-----------+                              |  + transform       |
                                             +----------+---------+
                                                        |
                              +-------------------------+------------------+
                              |                                            |
                              v                                            v
                     +----------------+                          +------------------+
                     |   DynamoDB     |                          |   S3 bucket      |
                     |  (clean data)  |                          |  (processed/     |
                     +----------------+                          |   rejected/)     |
                                                                  +------------------+

 CloudWatch Alarms watch Lambda errors + DLQ depth -> SNS email alert
 GitHub Actions runs `terraform plan` on PR, `terraform apply` on merge to main
```

**Why this design:**
- **Event-driven, not polling** — Lambda only runs (and only costs money) when
  a file actually lands in S3.
- **Dead-letter queue (SQS)** catches records that fail processing instead of
  silently dropping them — this is the kind of reliability detail that shows
  production thinking, not just a tutorial follow-along.
- **Separation of raw/processed/rejected** in S3 gives you an audit trail —
  you can always see what came in vs what made it to the database vs what
  failed and why.

## AWS services used (all Free Tier eligible)

| Service | Purpose | Free tier limit |
|---|---|---|
| S3 | Raw + processed file storage | 5 GB storage, 12 months |
| Lambda | ETL compute | 1M requests/month, always free |
| DynamoDB | Clean data store | 25 GB storage, always free |
| SQS | Dead-letter queue for failed records | 1M requests/month, always free |
| CloudWatch | Logs, metrics, alarms | 10 custom metrics, always free |
| SNS | Alert email on failures | 1,000 emails/month, always free |

## Repo structure

```
aws-data-pipeline/
├── terraform/          # Infrastructure as Code
│   ├── main.tf          # S3, Lambda, DynamoDB, IAM, CloudWatch, SNS
│   ├── variables.tf
│   └── outputs.tf
├── src/
│   └── lambda_handler.py   # ETL logic
├── tests/
│   └── test_handler.py     # Unit tests (pytest + moto, no AWS account needed)
├── sample_data/
│   └── sample_orders.csv   # Test file to upload
├── .github/workflows/
│   └── deploy.yml          # CI/CD: test -> plan -> apply
└── requirements.txt
```

## Setup (from scratch)

### 1. Prerequisites
- AWS account with a **budget alert set at $1** (Billing console → Budgets)
- AWS CLI configured (`aws configure`) with an IAM user that has
  programmatic access (do NOT use your root account)
- Terraform >= 1.5 installed
- Python 3.12

### 2. Local setup
```bash
git clone <your-repo-url>
cd aws-data-pipeline
pip install -r requirements.txt
pytest tests/ -v          # run tests locally first, no AWS needed (uses moto)
```

### 3. Deploy manually (first time, to confirm it works)
```bash
cd terraform
terraform init
terraform plan            # review what will be created
terraform apply           # type 'yes' to confirm
```

Terraform will print the S3 bucket name as an output.

### 4. Test the pipeline
```bash
aws s3 cp ../sample_data/sample_orders.csv s3://<bucket-name-from-output>/raw/
```
Wait ~10 seconds, then check:
```bash
aws dynamodb scan --table-name orders-table
```
You should see the parsed rows. Check `s3://<bucket>/processed/` and
`s3://<bucket>/rejected/` too.

### 5. Set up CI/CD (GitHub Actions)
1. In your GitHub repo settings → Secrets → Actions, add:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
2. Push to a branch and open a PR → Actions will run `terraform plan` and
   post the diff as a PR comment.
3. Merge to `main` → Actions runs `terraform apply` automatically.

### 6. Tear down (IMPORTANT — do this when you're done demoing)
```bash
cd terraform
terraform destroy
```
This project costs effectively $0 sitting idle, but destroying it when
you're not actively using it for interviews/demos is still good practice.

## What to put on your resume

> Built a serverless ETL pipeline on AWS (Lambda, S3, DynamoDB, SQS,
> CloudWatch) provisioned entirely via Terraform with a GitHub Actions
> CI/CD pipeline for automated plan/apply on every commit. Implemented a
> dead-letter queue for failed record handling and CloudWatch alarms with
> SNS alerting.

## Possible extensions (if you have extra time)
- Add a Step Functions state machine to orchestrate multi-stage processing
- Add a QuickSight dashboard on top of the DynamoDB data (via S3 export)
- Swap DynamoDB for Athena + Glue for a more "data engineer" flavored version
