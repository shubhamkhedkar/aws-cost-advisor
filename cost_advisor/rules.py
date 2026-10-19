"""Rule-based findings. Each finding: severity, category, resource, region, issue,
recommendation, est_monthly_savings_usd (or None)."""
from . import pricing as P

LOW_CPU = 5.0
SNAPSHOT_AGE_DAYS = 90


def _f(sev, cat, res, region, issue, rec, savings=None, cmd=None):
    return {"severity": sev, "category": cat, "resource": res, "region": region,
            "issue": issue, "recommendation": rec,
            "est_monthly_savings_usd": round(savings, 2) if savings is not None else None,
            "cli_hint": cmd}


def analyze(data):
    out = []
    for rd in data["regions"]:
        rg = rd["region"]
        vols = {v["id"]: v for v in rd["volumes"]}
        for i in rd["ec2"]:
            cost = P.ec2_monthly(i["type"])
            if i["state"] == "running" and i["avg_cpu_14d"] is not None and i["avg_cpu_14d"] < LOW_CPU:
                out.append(_f("high" if (cost or 0) > 20 else "medium", "EC2", i["id"], rg,
                    f"{i['type']} running {i['uptime_days']}d with avg CPU {i['avg_cpu_14d']}% (14d)",
                    "Downsize (e.g. t3.micro/t4g.micro, free-tier eligible) or stop when not in use",
                    cost / 2 if cost else None,
                    f"aws ec2 stop-instances --instance-ids {i['id']} --region {rg}"))
            if i["state"] == "running" and not i["type"].startswith(("t2.micro", "t3.micro")) and cost and cost > 15:
                out.append(_f("medium", "EC2", i["id"], rg,
                    f"{i['type']} (~${cost}/mo) is outside free tier",
                    "Use t2.micro/t3.micro for learning, or schedule start/stop", None, None))
            if i["state"] == "stopped" and i["volumes"]:
                gb = sum(vols.get(v, {}).get("size_gb", 0) for v in i["volumes"])
                vt = vols.get(i["volumes"][0], {}).get("type", "gp2")
                out.append(_f("medium", "EBS", i["id"], rg,
                    f"Stopped instance still has {len(i['volumes'])} EBS volume(s), {gb} GB billed",
                    "Snapshot + terminate the instance if no longer needed",
                    gb * P.EBS_GB_MONTH.get(vt, 0.1),
                    f"aws ec2 terminate-instances --instance-ids {i['id']} --region {rg}"))
        for v in rd["volumes"]:
            price = P.EBS_GB_MONTH.get(v["type"], 0.1)
            if v["state"] == "available":
                out.append(_f("high", "EBS", v["id"], rg,
                    f"Unattached {v['type']} volume, {v['size_gb']} GB",
                    "Snapshot if needed, then delete", v["size_gb"] * price,
                    f"aws ec2 delete-volume --volume-id {v['id']} --region {rg}"))
            if v["type"] == "gp2" and v["state"] != "available":
                out.append(_f("low", "EBS", v["id"], rg, f"gp2 volume ({v['size_gb']} GB)",
                    "Migrate to gp3 (~20% cheaper, better baseline IOPS), no downtime",
                    v["size_gb"] * (P.EBS_GB_MONTH["gp2"] - P.EBS_GB_MONTH["gp3"]),
                    f"aws ec2 modify-volume --volume-id {v['id']} --volume-type gp3 --region {rg}"))
        for s in rd["snapshots"]:
            if s["age_days"] > SNAPSHOT_AGE_DAYS:
                out.append(_f("low", "EBS Snapshot", s["id"], rg,
                    f"Snapshot is {s['age_days']} days old ({s['size_gb']} GB volume size)",
                    "Delete if obsolete, or use Data Lifecycle Manager retention",
                    s["size_gb"] * P.SNAPSHOT_GB_MONTH,
                    f"aws ec2 delete-snapshot --snapshot-id {s['id']} --region {rg}"))
        for e in rd["eips"]:
            if not e["associated"]:
                out.append(_f("high", "Elastic IP", e["public_ip"], rg,
                    "Elastic IP not associated with any resource",
                    "Release it", P.EIP_HOURLY * P.HOURS,
                    f"aws ec2 release-address --allocation-id {e['allocation_id']} --region {rg}"))
        for n in rd["nat_gateways"]:
            idle = n["bytes_out_14d"] in (None, 0)
            out.append(_f("high", "NAT Gateway", n["id"], rg,
                f"NAT gateway running (~${round(P.NAT_HOURLY * P.HOURS, 2)}/mo + data)"
                + (" with little/no traffic" if idle else ""),
                "Delete when not needed; for labs use public subnets or a NAT instance",
                P.NAT_HOURLY * P.HOURS,
                f"aws ec2 delete-nat-gateway --nat-gateway-id {n['id']} --region {rg}"))
        for lb in rd["load_balancers"]:
            if lb["targets"] == 0 or lb["healthy"] == 0 or (lb["requests_14d"] or 0) < 100:
                why = "no registered targets" if lb["targets"] == 0 else (
                    "no healthy targets" if lb["healthy"] == 0 else "very low request count")
                out.append(_f("high", "Load Balancer", lb["name"], rg, f"{lb['type']} LB with {why}",
                    "Delete idle load balancer", P.ALB_HOURLY * P.HOURS,
                    f"aws elbv2 delete-load-balancer --load-balancer-arn <arn-of-{lb['name']}> --region {rg}"))
        for db in rd["rds"]:
            cost = P.rds_monthly(db["class"])
            if db["multi_az"]:
                out.append(_f("high", "RDS", db["id"], rg, "Multi-AZ enabled (doubles instance cost)",
                    "Disable Multi-AZ for dev/learning databases", cost,
                    f"aws rds modify-db-instance --db-instance-identifier {db['id']} --no-multi-az --apply-immediately --region {rg}"))
            if db["avg_cpu_14d"] is not None and db["avg_cpu_14d"] < LOW_CPU:
                out.append(_f("medium", "RDS", db["id"], rg,
                    f"{db['class']} avg CPU {db['avg_cpu_14d']}% (14d)",
                    "Downsize to db.t3.micro/db.t4g.micro or stop when idle (auto-restarts after 7 days)",
                    cost / 2 if cost else None,
                    f"aws rds stop-db-instance --db-instance-identifier {db['id']} --region {rg}"))
            if db["class"] not in ("db.t2.micro", "db.t3.micro", "db.t4g.micro"):
                out.append(_f("medium", "RDS", db["id"], rg, f"{db['class']} not free-tier eligible",
                    "Use db.t3.micro / db.t4g.micro for free tier", None, None))
            if (db["storage_gb"] or 0) > 20:
                out.append(_f("low", "RDS", db["id"], rg, f"{db['storage_gb']} GB storage (free tier: 20 GB)",
                    "Storage can't shrink in place; recreate smaller if this is a lab DB",
                    (db["storage_gb"] - 20) * P.RDS_GB_MONTH, None))
        for fn in rd["lambda"]:
            if (fn["memory_mb"] or 0) >= 1024:
                out.append(_f("low", "Lambda", fn["name"], rg, f"{fn['memory_mb']} MB memory configured",
                    "Right-size memory (try AWS Lambda Power Tuning)", None,
                    f"aws lambda update-function-configuration --function-name {fn['name']} --memory-size 256 --region {rg}"))
            if fn["invocations_14d"] in (None, 0):
                out.append(_f("info", "Lambda", fn["name"], rg, "No invocations in 14 days",
                    "Delete if unused (no idle cost, but reduces clutter/risk)", 0, None))
    for b in data["s3"]:
        if b["lifecycle_policy"] is False:
            out.append(_f("low", "S3", b["name"], b["region"],
                f"No lifecycle policy (size: {b['size_gb'] if b['size_gb'] is not None else 'unknown'} GB)",
                "Add lifecycle rules (transition to IA/Glacier, expire old versions/incomplete uploads)",
                None, f"aws s3api put-bucket-lifecycle-configuration --bucket {b['name']} --lifecycle-configuration file://lifecycle.json"))
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    out.sort(key=lambda f: (order[f["severity"]], -(f["est_monthly_savings_usd"] or 0)))
    return out


def total_savings(findings):
    return round(sum(f["est_monthly_savings_usd"] or 0 for f in findings), 2)
