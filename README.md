# aws-cost-advisor

A **read-only** Python CLI that scans your AWS account, flags wasteful resources with
rule-based checks (with estimated monthly savings), and optionally asks an LLM for
prioritized, concrete recommendations including the AWS CLI command to apply each.
**The tool never changes anything** — it only uses `describe*/list*/get*` APIs.

Built for learners on free-tier accounts (default region `ap-south-1`).

## What it checks

| Area | Checks |
|---|---|
| EC2 | type, state, uptime, 14-day avg CPU (CloudWatch); low-CPU and non-free-tier instances; stopped instances still paying for EBS |
| EBS | unattached volumes, gp2 → gp3, snapshots older than 90 days |
| Networking | unassociated Elastic IPs, NAT gateways (and their traffic) |
| ELBv2 | load balancers with no targets / no healthy targets / < 100 requests in 14 days |
| RDS | CPU, Multi-AZ, instance class vs free tier, storage > 20 GB |
| S3 | size (CloudWatch `BucketSizeBytes`), lifecycle policy presence |
| Lambda | memory size, 14-day invocations |
| Cost Explorer | last-30-day cost by service (us-east-1; skipped gracefully if denied/not enabled) |

## Setup

```bash
cd aws-cost-advisor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
aws configure            # or AWS_PROFILE / env vars — standard credential chain
```

### IAM policy (least privilege, read-only)

Create a dedicated IAM user/role and attach [`iam-policy.json`](iam-policy.json):

```bash
aws iam create-policy --policy-name AwsCostAdvisorReadOnly --policy-document file://iam-policy.json
aws iam attach-user-policy --user-name cost-advisor \
  --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/AwsCostAdvisorReadOnly
```

> Cost Explorer must be enabled once in the Billing console; each `GetCostAndUsage`
> call costs $0.01. Drop `ce:GetCostAndUsage` if you want zero API cost.

### AI (optional)

```bash
export AI_API_KEY=sk-...                         # required for AI step
export AI_BASE_URL=https://api.openai.com/v1     # any OpenAI-compatible endpoint (default)
export AI_MODEL=gpt-4o-mini                      # default
```

Only a compact JSON summary is sent (resource IDs/types, metrics, findings) — no
credentials, account ID, ARNs, or tags other than resource names. Without a key,
or with `--no-ai`, you get the rule-based report.

## Usage

```bash
python aws_cost_advisor.py                          # ap-south-1, terminal output
python aws_cost_advisor.py -o report.md             # also write markdown report
python aws_cost_advisor.py --all-regions --no-ai
python aws_cost_advisor.py --profile learner --region us-east-1
python -m cost_advisor --help
```

| Flag | Meaning |
|---|---|
| `--region` | Region to scan (default `ap-south-1`) |
| `--all-regions` | Scan every enabled region |
| `--profile` | AWS CLI profile |
| `--output, -o` | Markdown report path |
| `--no-ai` | Skip the LLM step |

## Sample output

See [`sample-report.md`](sample-report.md) (generated against mocked resources). Excerpt:

```
| high | RDS | `labdb` | Multi-AZ enabled (doubles instance cost) | Disable Multi-AZ ... | $140.16 (~₹11773) |
| high | NAT Gateway | `nat-...` | NAT gateway running (~$40.88/mo + data) ... | Delete when not needed ... | $40.88 (~₹3434) |
| high | Load Balancer | `idle-alb` | application LB with no registered targets | Delete idle load balancer | $17.45 (~₹1466) |
| high | Elastic IP | `x.x.x.x` | Elastic IP not associated with any resource | Release it | $3.65 (~₹307) |
```

## Tests (no AWS credentials needed)

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests use [moto](https://github.com/getmoto/moto) to create wasteful resources
(idle m5.large, stopped instance, unattached gp2 volume, free EIP, NAT gateway,
target-less ALB, Multi-AZ RDS, S3 bucket without lifecycle, 2 GB Lambda), verify
findings, mock the AI HTTP call, and assert the collector only uses read-only APIs.

## Limitations

- Prices are hard-coded approximate on-demand figures (USD, ~ap-south-1); INR uses ~84/USD. Verify with the AWS Pricing Calculator.
- Savings are estimates and may overlap (e.g. downsize vs. stop the same instance).
- Classic ELBs, ECS/EKS, DynamoDB, CloudFront, data transfer, and Savings Plans/RIs aren't analyzed.
- S3 size relies on daily CloudWatch storage metrics (StandardStorage only; new buckets show "unknown").
- AI output is advisory — always review commands before running, especially deletes.

## License

MIT
