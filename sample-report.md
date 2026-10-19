# AWS Cost Advisor Report

- Generated: 2026-10-20 00:36
- Regions: ap-south-1
- Findings: 15 | Estimated savings: **$256.46 (~₹21543)/month**

## Last 30 days cost by service

Period 2026-09-20..2026-10-20, total **0 USD**

| Service | Cost |
|---|---:|

## Rule-based findings

| Severity | Category | Resource | Region | Issue | Recommendation | Est. savings/mo |
|---|---|---|---|---|---|---:|
| high | RDS | `labdb` | ap-south-1 | Multi-AZ enabled (doubles instance cost) | Disable Multi-AZ for dev/learning databases | $140.16 (~₹11773) |
| high | NAT Gateway | `nat-573ede7b601ae8db7` | ap-south-1 | NAT gateway running (~$40.88/mo + data) with little/no traffic | Delete when not needed; for labs use public subnets or a NAT instance | $40.88 (~₹3434) |
| high | EC2 | `i-c7619eca2d1986c8a` | ap-south-1 | m5.large running 0.0d with avg CPU 1.5% (14d) | Downsize (e.g. t3.micro/t4g.micro, free-tier eligible) or stop when not in use | $36.87 (~₹3097) |
| high | Load Balancer | `idle-alb` | ap-south-1 | application LB with no registered targets | Delete idle load balancer | $17.45 (~₹1466) |
| high | EBS | `vol-812b6c39cbbda03d5` | ap-south-1 | Unattached gp2 volume, 50 GB | Snapshot if needed, then delete | $5.70 (~₹479) |
| high | Elastic IP | `127.179.195.223` | ap-south-1 | Elastic IP not associated with any resource | Release it | $3.65 (~₹307) |
| medium | EBS | `i-a28cdef2a07a966cb` | ap-south-1 | Stopped instance still has 1 EBS volume(s), 8 GB billed | Snapshot + terminate the instance if no longer needed | $0.91 (~₹76) |
| medium | EC2 | `i-c7619eca2d1986c8a` | ap-south-1 | m5.large (~$73.73/mo) is outside free tier | Use t2.micro/t3.micro for learning, or schedule start/stop | - |
| medium | RDS | `labdb` | ap-south-1 | db.m5.large not free-tier eligible | Use db.t3.micro / db.t4g.micro for free tier | - |
| low | RDS | `labdb` | ap-south-1 | 100 GB storage (free tier: 20 GB) | Storage can't shrink in place; recreate smaller if this is a lab DB | $10.48 (~₹880) |
| low | EBS | `vol-28dcbe315429a345b` | ap-south-1 | gp2 volume (8 GB) | Migrate to gp3 (~20% cheaper, better baseline IOPS), no downtime | $0.18 (~₹15) |
| low | EBS | `vol-1af274f8054092f25` | ap-south-1 | gp2 volume (8 GB) | Migrate to gp3 (~20% cheaper, better baseline IOPS), no downtime | $0.18 (~₹15) |
| low | Lambda | `bigfn` | ap-south-1 | 2048 MB memory configured | Right-size memory (try AWS Lambda Power Tuning) | - |
| low | S3 | `shubham-logs` | ap-south-1 | No lifecycle policy (size: 0.0 GB) | Add lifecycle rules (transition to IA/Glacier, expire old versions/incomplete uploads) | - |
| info | Lambda | `bigfn` | ap-south-1 | No invocations in 14 days | Delete if unused (no idle cost, but reduces clutter/risk) | $0.00 (~₹0) |

### Suggested commands (review first — the tool never runs these)

```bash
# RDS labdb: Disable Multi-AZ for dev/learning databases
aws rds modify-db-instance --db-instance-identifier labdb --no-multi-az --apply-immediately --region ap-south-1
# NAT Gateway nat-573ede7b601ae8db7: Delete when not needed; for labs use public subnets or a NAT instance
aws ec2 delete-nat-gateway --nat-gateway-id nat-573ede7b601ae8db7 --region ap-south-1
# EC2 i-c7619eca2d1986c8a: Downsize (e.g. t3.micro/t4g.micro, free-tier eligible) or stop when not in use
aws ec2 stop-instances --instance-ids i-c7619eca2d1986c8a --region ap-south-1
# Load Balancer idle-alb: Delete idle load balancer
aws elbv2 delete-load-balancer --load-balancer-arn <arn-of-idle-alb> --region ap-south-1
# EBS vol-812b6c39cbbda03d5: Snapshot if needed, then delete
aws ec2 delete-volume --volume-id vol-812b6c39cbbda03d5 --region ap-south-1
# Elastic IP 127.179.195.223: Release it
aws ec2 release-address --allocation-id eipalloc-293f705e88e2b7c46 --region ap-south-1
# EBS i-a28cdef2a07a966cb: Snapshot + terminate the instance if no longer needed
aws ec2 terminate-instances --instance-ids i-a28cdef2a07a966cb --region ap-south-1
# EBS vol-28dcbe315429a345b: Migrate to gp3 (~20% cheaper, better baseline IOPS), no downtime
aws ec2 modify-volume --volume-id vol-28dcbe315429a345b --volume-type gp3 --region ap-south-1
# EBS vol-1af274f8054092f25: Migrate to gp3 (~20% cheaper, better baseline IOPS), no downtime
aws ec2 modify-volume --volume-id vol-1af274f8054092f25 --volume-type gp3 --region ap-south-1
# Lambda bigfn: Right-size memory (try AWS Lambda Power Tuning)
aws lambda update-function-configuration --function-name bigfn --memory-size 256 --region ap-south-1
# S3 shubham-logs: Add lifecycle rules (transition to IA/Glacier, expire old versions/incomplete uploads)
aws s3api put-bucket-lifecycle-configuration --bucket shubham-logs --lifecycle-configuration file://lifecycle.json
```

## AI recommendations

_AI step skipped (no AI_API_KEY, --no-ai, or error)._

_Prices are approximate on-demand estimates; verify with the AWS Pricing Calculator._
