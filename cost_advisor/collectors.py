"""Read-only collectors. Only describe*/list*/get* calls are used."""
import datetime as dt
import logging
from botocore.exceptions import ClientError, BotoCoreError

log = logging.getLogger(__name__)
UTC = dt.timezone.utc


def _now():
    return dt.datetime.now(UTC)


def _safe(fn, errors, label, default=None):
    try:
        return fn()
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        errors.append(f"{label}: {code}")
        return default


def _avg_metric(cw, ns, metric, dims, days=14, stat="Average", period=86400):
    end = _now()
    r = cw.get_metric_statistics(Namespace=ns, MetricName=metric, Dimensions=dims,
                                 StartTime=end - dt.timedelta(days=days), EndTime=end,
                                 Period=period, Statistics=[stat])
    pts = [p[stat] for p in r.get("Datapoints", [])]
    if not pts:
        return None
    return round(sum(pts) / len(pts), 2) if stat == "Average" else round(sum(pts), 2)


def _paginate(client, op, key, **kw):
    out = []
    for page in client.get_paginator(op).paginate(**kw):
        out.extend(page.get(key, []))
    return out


def collect_region(session, region, errors):
    ec2 = session.client("ec2", region_name=region)
    cw = session.client("cloudwatch", region_name=region)
    d = {"region": region}

    # EC2
    def ec2_instances():
        res = []
        for r in _paginate(ec2, "describe_instances", "Reservations"):
            for i in r["Instances"]:
                iid = i["InstanceId"]
                cpu = _safe(lambda: _avg_metric(cw, "AWS/EC2", "CPUUtilization",
                            [{"Name": "InstanceId", "Value": iid}]), errors, f"cw cpu {iid}")
                launch = i.get("LaunchTime")
                name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
                res.append({
                    "id": iid, "name": name, "type": i["InstanceType"],
                    "state": i["State"]["Name"],
                    "uptime_days": round((_now() - launch).total_seconds() / 86400, 1) if launch else None,
                    "avg_cpu_14d": cpu,
                    "volumes": [b["Ebs"]["VolumeId"] for b in i.get("BlockDeviceMappings", []) if "Ebs" in b],
                })
        return res
    d["ec2"] = _safe(ec2_instances, errors, f"{region} ec2", [])

    # EBS
    def vols():
        return [{"id": v["VolumeId"], "type": v["VolumeType"], "size_gb": v["Size"],
                 "state": v["State"], "attached_to": [a["InstanceId"] for a in v.get("Attachments", [])]}
                for v in _paginate(ec2, "describe_volumes", "Volumes")]
    d["volumes"] = _safe(vols, errors, f"{region} ebs", [])

    def snaps():
        return [{"id": s["SnapshotId"], "size_gb": s["VolumeSize"],
                 "age_days": (_now() - s["StartTime"]).days, "volume_id": s.get("VolumeId")}
                for s in _paginate(ec2, "describe_snapshots", "Snapshots", OwnerIds=["self"])]
    d["snapshots"] = _safe(snaps, errors, f"{region} snapshots", [])

    def eips():
        return [{"public_ip": a.get("PublicIp"), "allocation_id": a.get("AllocationId"),
                 "associated": bool(a.get("AssociationId") or a.get("InstanceId"))}
                for a in ec2.describe_addresses()["Addresses"]]
    d["eips"] = _safe(eips, errors, f"{region} eip", [])

    def nats():
        out = []
        for n in _paginate(ec2, "describe_nat_gateways", "NatGateways"):
            if n["State"] not in ("available", "pending"):
                continue
            gb = _safe(lambda: _avg_metric(cw, "AWS/NATGateway", "BytesOutToDestination",
                       [{"Name": "NatGatewayId", "Value": n["NatGatewayId"]}], stat="Sum"),
                       errors, "cw nat")
            out.append({"id": n["NatGatewayId"], "state": n["State"],
                        "bytes_out_14d": gb})
        return out
    d["nat_gateways"] = _safe(nats, errors, f"{region} nat", [])

    # ELBv2
    def elbs():
        elb = session.client("elbv2", region_name=region)
        out = []
        for lb in _paginate(elb, "describe_load_balancers", "LoadBalancers"):
            arn = lb["LoadBalancerArn"]
            try:
                tgs = elb.describe_target_groups(LoadBalancerArn=arn)["TargetGroups"]
            except ClientError as e:
                if e.response["Error"]["Code"] != "TargetGroupNotFound":
                    raise
                tgs = []
            healthy = 0
            total = 0
            for tg in tgs:
                th = elb.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])["TargetHealthDescriptions"]
                total += len(th)
                healthy += sum(1 for t in th if t["TargetHealth"]["State"] == "healthy")
            dim = "/".join(arn.split(":loadbalancer/")[-1].split("/"))
            reqs = _safe(lambda: _avg_metric(cw, "AWS/ApplicationELB", "RequestCount",
                         [{"Name": "LoadBalancer", "Value": dim}], stat="Sum"), errors, "cw elb")
            out.append({"name": lb["LoadBalancerName"], "type": lb["Type"],
                        "target_groups": len(tgs), "targets": total, "healthy": healthy,
                        "requests_14d": reqs})
        return out
    d["load_balancers"] = _safe(elbs, errors, f"{region} elbv2", [])

    # RDS
    def rds():
        c = session.client("rds", region_name=region)
        out = []
        for db in _paginate(c, "describe_db_instances", "DBInstances"):
            cpu = _safe(lambda: _avg_metric(cw, "AWS/RDS", "CPUUtilization",
                        [{"Name": "DBInstanceIdentifier", "Value": db["DBInstanceIdentifier"]}]),
                        errors, "cw rds")
            out.append({"id": db["DBInstanceIdentifier"], "class": db["DBInstanceClass"],
                        "engine": db["Engine"], "status": db["DBInstanceStatus"],
                        "multi_az": db.get("MultiAZ", False),
                        "storage_gb": db.get("AllocatedStorage"),
                        "storage_type": db.get("StorageType"), "avg_cpu_14d": cpu})
        return out
    d["rds"] = _safe(rds, errors, f"{region} rds", [])

    # Lambda
    def lambdas():
        c = session.client("lambda", region_name=region)
        out = []
        for f in _paginate(c, "list_functions", "Functions"):
            inv = _safe(lambda: _avg_metric(cw, "AWS/Lambda", "Invocations",
                        [{"Name": "FunctionName", "Value": f["FunctionName"]}], stat="Sum"),
                        errors, "cw lambda")
            out.append({"name": f["FunctionName"], "memory_mb": f.get("MemorySize"),
                        "runtime": f.get("Runtime"), "invocations_14d": inv})
        return out
    d["lambda"] = _safe(lambdas, errors, f"{region} lambda", [])
    return d


def collect_s3(session, errors):
    s3 = session.client("s3")
    out = []
    buckets = _safe(lambda: s3.list_buckets()["Buckets"], errors, "s3 list", []) or []
    for b in buckets:
        name = b["Name"]
        loc = _safe(lambda: s3.get_bucket_location(Bucket=name).get("LocationConstraint"),
                    errors, f"s3 location {name}") or "us-east-1"
        cw = session.client("cloudwatch", region_name=loc)
        size = _safe(lambda: _avg_metric(cw, "AWS/S3", "BucketSizeBytes",
                     [{"Name": "BucketName", "Value": name},
                      {"Name": "StorageType", "Value": "StandardStorage"}], days=3),
                     errors, f"cw s3 {name}")
        try:
            s3.get_bucket_lifecycle_configuration(Bucket=name)
            lifecycle = True
        except ClientError as e:
            code = e.response["Error"]["Code"]
            lifecycle = False if code == "NoSuchLifecycleConfiguration" else None
            if lifecycle is None:
                errors.append(f"s3 lifecycle {name}: {code}")
        out.append({"name": name, "region": loc,
                    "size_gb": round(size / 1024**3, 3) if size is not None else None,
                    "lifecycle_policy": lifecycle})
    return out


def collect_costs(session, errors):
    ce = session.client("ce", region_name="us-east-1")
    end = dt.date.today()
    start = end - dt.timedelta(days=30)
    try:
        r = ce.get_cost_and_usage(TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                                  Granularity="MONTHLY", Metrics=["UnblendedCost"],
                                  GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}])
    except (ClientError, BotoCoreError) as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        errors.append(f"cost explorer: {code} (enable CE / grant ce:GetCostAndUsage)")
        return None
    totals = {}
    unit = "USD"
    for res in r.get("ResultsByTime", []):
        for g in res.get("Groups", []):
            amt = g["Metrics"]["UnblendedCost"]
            unit = amt.get("Unit", unit)
            totals[g["Keys"][0]] = totals.get(g["Keys"][0], 0) + float(amt["Amount"])
    svc = sorted(({"service": k, "cost": round(v, 2)} for k, v in totals.items() if v > 0.001),
                 key=lambda x: -x["cost"])
    return {"period": f"{start}..{end}", "unit": unit, "total": round(sum(totals.values()), 2),
            "by_service": svc}


def list_regions(session, default):
    try:
        return [r["RegionName"] for r in
                session.client("ec2", region_name=default).describe_regions()["Regions"]]
    except (ClientError, BotoCoreError):
        return [default]


def collect_all(session, regions):
    errors = []
    data = {"regions": [collect_region(session, r, errors) for r in regions],
            "s3": collect_s3(session, errors),
            "cost_explorer": collect_costs(session, errors)}
    data["errors"] = errors
    return data
