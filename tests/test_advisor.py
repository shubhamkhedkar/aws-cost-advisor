import datetime as dt
import io
import json
import os
import zipfile
from unittest import mock

import boto3
import pytest
from moto import mock_aws

from cost_advisor import ai, collectors, rules, report, cli

R = "ap-south-1"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(k, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", R)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)


def make_waste():
    ec2 = boto3.client("ec2", region_name=R)
    ami = ec2.describe_images()["Images"][0]["ImageId"]
    running = ec2.run_instances(ImageId=ami, InstanceType="m5.large", MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]
    stopped = ec2.run_instances(ImageId=ami, InstanceType="t3.micro", MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]
    ec2.stop_instances(InstanceIds=[stopped])
    cw = boto3.client("cloudwatch", region_name=R)
    cw.put_metric_data(Namespace="AWS/EC2", MetricData=[{
        "MetricName": "CPUUtilization", "Dimensions": [{"Name": "InstanceId", "Value": running}],
        "Value": 1.5, "Timestamp": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)}])
    vol = ec2.create_volume(AvailabilityZone=f"{R}a", Size=50, VolumeType="gp2")["VolumeId"]
    ec2.create_snapshot(VolumeId=vol)
    ec2.allocate_address(Domain="vpc")
    vpc = ec2.describe_vpcs()["Vpcs"][0]["VpcId"]
    subs = [s["SubnetId"] for s in ec2.describe_subnets()["Subnets"]][:2]
    eip2 = ec2.allocate_address(Domain="vpc")["AllocationId"]
    ec2.create_nat_gateway(SubnetId=subs[0], AllocationId=eip2)
    elb = boto3.client("elbv2", region_name=R)
    elb.create_load_balancer(Name="idle-alb", Subnets=subs)
    rds = boto3.client("rds", region_name=R)
    rds.create_db_instance(DBInstanceIdentifier="labdb", DBInstanceClass="db.m5.large", Engine="mysql",
                           MasterUsername="admin", MasterUserPassword="password123", AllocatedStorage=100,
                           MultiAZ=True)
    s3 = boto3.client("s3", region_name=R)
    s3.create_bucket(Bucket="shubham-logs", CreateBucketConfiguration={"LocationConstraint": R})
    iam = boto3.client("iam", region_name=R)
    role = iam.create_role(RoleName="lr", AssumeRolePolicyDocument="{}")["Role"]["Arn"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("h.py", "def h(e,c): return 1")
    boto3.client("lambda", region_name=R).create_function(
        FunctionName="bigfn", Runtime="python3.12", Role=role, Handler="h.h",
        Code={"ZipFile": buf.getvalue()}, MemorySize=2048)
    return {"running": running, "stopped": stopped, "vol": vol}


@mock_aws
def test_findings_detected():
    ids = make_waste()
    data = collectors.collect_all(boto3.Session(region_name=R), [R])
    f = rules.analyze(data)
    by = lambda cat: [x for x in f if x["category"] == cat]
    issues = " | ".join(x["issue"] for x in f)
    assert any(x["resource"] == ids["running"] and "avg CPU 1.5" in x["issue"] for x in by("EC2"))
    assert any(x["resource"] == ids["stopped"] for x in by("EBS"))
    assert any(x["resource"] == ids["vol"] and "Unattached" in x["issue"] for x in by("EBS"))
    assert any("gp2" in x["issue"] and "gp3" in (x["cli_hint"] or "") for x in by("EBS"))
    assert len(by("Elastic IP")) == 1  # the NAT one is associated
    assert by("NAT Gateway")
    assert any(x["resource"] == "idle-alb" for x in by("Load Balancer"))
    rds_issues = " ".join(x["issue"] for x in by("RDS"))
    assert "Multi-AZ" in rds_issues and "free-tier" in rds_issues and "100 GB" in rds_issues
    assert any(x["resource"] == "bigfn" for x in by("Lambda"))
    assert any(x["resource"] == "shubham-logs" for x in by("S3"))
    assert rules.total_savings(f) > 50, issues
    # Cost Explorer: moto returns data or an error; either must not crash
    assert "cost_explorer" in data


def test_old_snapshot_rule():
    data = {"regions": [{"region": R, "ec2": [], "volumes": [], "eips": [], "nat_gateways": [],
                         "load_balancers": [], "rds": [], "lambda": [],
                         "snapshots": [{"id": "snap-1", "size_gb": 30, "age_days": 200, "volume_id": "v"}]}],
            "s3": [], "errors": []}
    f = rules.analyze(data)
    assert f[0]["category"] == "EBS Snapshot" and f[0]["est_monthly_savings_usd"] == 1.5


@mock_aws
def test_cost_explorer_permission_error_handled():
    from botocore.exceptions import ClientError
    errs = []
    with mock.patch("botocore.client.BaseClient._make_api_call",
                    side_effect=ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetCostAndUsage")):
        assert collectors.collect_costs(boto3.Session(region_name=R), errs) is None
    assert "AccessDenied" in errs[0]


@mock_aws
def test_summary_has_no_account_id_or_secrets():
    make_waste()
    data = collectors.collect_all(boto3.Session(region_name=R), [R])
    s = json.dumps(ai.build_summary(data, rules.analyze(data)), default=str)
    assert "123456789012" not in s and "password123" not in s and "arn:aws" not in s


@mock_aws
def test_cli_with_mocked_ai(tmp_path, monkeypatch):
    make_waste()
    monkeypatch.setenv("AI_API_KEY", "sk-test")
    fake = mock.Mock()
    fake.json.return_value = {"choices": [{"message": {"content": "1. **Delete NAT gateway** save $40"}}]}
    fake.raise_for_status.return_value = None
    out = tmp_path / "r.md"
    with mock.patch("cost_advisor.ai.requests.post", return_value=fake) as post:
        assert cli.main(["--output", str(out)]) == 0
    body = post.call_args.kwargs["json"]
    assert body["model"] == "gpt-4o-mini"
    assert post.call_args.args[0] == "https://api.openai.com/v1/chat/completions"
    md = out.read_text()
    assert "Delete NAT gateway" in md and "Rule-based findings" in md and "idle-alb" in md


@mock_aws
def test_cli_no_ai_and_ai_failure(tmp_path, monkeypatch):
    make_waste()
    out = tmp_path / "r.md"
    assert cli.main(["--no-ai", "-o", str(out)]) == 0
    assert "AI step skipped" in out.read_text()
    monkeypatch.setenv("AI_API_KEY", "sk-test")
    with mock.patch("cost_advisor.ai.requests.post", side_effect=ConnectionError("boom")):
        assert cli.main(["-o", str(out)]) == 0
    assert "AI step skipped" in out.read_text()


def test_read_only_calls_only():
    import re, pathlib
    src = pathlib.Path(collectors.__file__).read_text()
    calls = set(re.findall(r'\.(\w+)\(', src)) | set(re.findall(r'"(\w+)"', src))
    api = {c for c in calls if re.match(r"(describe|list|get|create|delete|put|modify|run|terminate|stop|start|update)_", c)}
    bad = {c for c in api if not c.startswith(("describe_", "list_", "get_"))}
    assert not bad, bad
