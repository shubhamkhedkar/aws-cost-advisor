"""Approximate on-demand prices (USD, Linux, ~ap-south-1). Estimates only."""
HOURS = 730
EC2_HOURLY = {
    "t2.nano": 0.0062, "t2.micro": 0.0124, "t2.small": 0.0248, "t2.medium": 0.0496,
    "t2.large": 0.0992, "t3.nano": 0.0056, "t3.micro": 0.0112, "t3.small": 0.0224,
    "t3.medium": 0.0448, "t3.large": 0.0896, "t3.xlarge": 0.1792, "t3a.micro": 0.0101,
    "t4g.micro": 0.0088, "t4g.small": 0.0176, "m5.large": 0.101, "m5.xlarge": 0.202,
    "c5.large": 0.085, "r5.large": 0.128,
}
EBS_GB_MONTH = {"gp2": 0.114, "gp3": 0.0912, "io1": 0.131, "io2": 0.131,
                "st1": 0.054, "sc1": 0.0174, "standard": 0.08}
SNAPSHOT_GB_MONTH = 0.05
EIP_HOURLY = 0.005
NAT_HOURLY = 0.056
ALB_HOURLY = 0.0239
CLB_HOURLY = 0.028
RDS_HOURLY = {"db.t3.micro": 0.021, "db.t3.small": 0.042, "db.t3.medium": 0.084,
              "db.t4g.micro": 0.019, "db.m5.large": 0.192}
RDS_GB_MONTH = 0.131

def ec2_monthly(itype):
    h = EC2_HOURLY.get(itype)
    return round(h * HOURS, 2) if h else None

def rds_monthly(cls):
    h = RDS_HOURLY.get(cls)
    return round(h * HOURS, 2) if h else None
