"""LLM step via an OpenAI-compatible Chat Completions API."""
import json
import os
import requests

SYSTEM = ("You are an AWS cost optimization expert advising a DevOps learner on a "
          "free-tier account with a ₹100 billing alert. Be concrete and prioritized.")

PROMPT = """Below is a JSON summary of resources in use and rule-based findings from a READ-ONLY scan.
Give a prioritized list (highest savings / risk first) of concrete cost optimization recommendations.
For each: title, why, estimated monthly savings (USD and approx INR), and the exact AWS CLI command
to apply it (the user will run it manually; mark destructive ones with a WARNING). Also mention free-tier
pitfalls and billing alarm/budget tips. Respond in GitHub Markdown, concise.

JSON:
{payload}"""


def build_summary(data, findings):
    """Compact summary; strips anything that could be a secret / account id."""
    regions = []
    for r in data["regions"]:
        regions.append({
            "region": r["region"],
            "ec2": [{k: i[k] for k in ("id", "type", "state", "uptime_days", "avg_cpu_14d")} for i in r["ec2"]],
            "ebs": [{k: v[k] for k in ("id", "type", "size_gb", "state")} for v in r["volumes"]],
            "snapshots": len(r["snapshots"]),
            "eips_unassociated": sum(1 for e in r["eips"] if not e["associated"]),
            "nat_gateways": len(r["nat_gateways"]),
            "load_balancers": [{k: l[k] for k in ("name", "type", "targets", "requests_14d")} for l in r["load_balancers"]],
            "rds": [{k: d[k] for k in ("id", "class", "engine", "multi_az", "storage_gb", "avg_cpu_14d")} for d in r["rds"]],
            "lambda": [{k: f[k] for k in ("name", "memory_mb", "invocations_14d")} for f in r["lambda"]],
        })
    regions = [r for r in regions if any(v for k, v in r.items() if k != "region")]
    return {"regions": regions,
            "s3": [{k: b[k] for k in ("name", "size_gb", "lifecycle_policy")} for b in data["s3"]],
            "cost_last_30d": data.get("cost_explorer"),
            "findings": [{k: f[k] for k in ("severity", "category", "resource", "issue", "est_monthly_savings_usd")}
                         for f in findings]}


def get_ai_recommendations(summary, timeout=60):
    key = os.environ.get("AI_API_KEY")
    if not key:
        return None
    base = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")
    r = requests.post(f"{base}/chat/completions", timeout=timeout,
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"model": model, "temperature": 0.2, "messages": [
                          {"role": "system", "content": SYSTEM},
                          {"role": "user", "content": PROMPT.format(payload=json.dumps(summary, default=str))}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
