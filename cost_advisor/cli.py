import argparse
import sys
import boto3
from botocore.exceptions import NoCredentialsError, ProfileNotFound
from rich.console import Console
from . import collectors, rules, ai, report


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="aws-cost-advisor",
                                description="Read-only AWS scan with rule-based + AI cost optimization suggestions.")
    p.add_argument("--region", default="ap-south-1", help="AWS region (default: ap-south-1)")
    p.add_argument("--all-regions", action="store_true", help="Scan all enabled regions")
    p.add_argument("--profile", help="AWS CLI profile name")
    p.add_argument("--output", "-o", help="Write markdown report to this file")
    p.add_argument("--no-ai", action="store_true", help="Skip the AI step")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    con = Console()
    try:
        session = boto3.Session(profile_name=a.profile, region_name=a.region)
        if session.get_credentials() is None:
            raise NoCredentialsError()
    except (ProfileNotFound, NoCredentialsError) as e:
        con.print(f"[red]AWS credentials problem: {e}. Run `aws configure` or set AWS_PROFILE.[/]")
        return 2
    regions = collectors.list_regions(session, a.region) if a.all_regions else [a.region]
    with con.status(f"Scanning {len(regions)} region(s) (read-only)..."):
        data = collectors.collect_all(session, regions)
    findings = rules.analyze(data)
    ai_text = None
    if not a.no_ai:
        try:
            with con.status("Asking AI for recommendations..."):
                ai_text = ai.get_ai_recommendations(ai.build_summary(data, findings))
            if ai_text is None:
                con.print("[dim]AI_API_KEY not set — showing rule-based report only.[/]")
        except Exception as e:  # network/API errors must not kill the report
            con.print(f"[yellow]AI step failed ({e}); falling back to rule-based report.[/]")
    report.print_terminal(data, findings, ai_text, regions, con)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as fh:
            fh.write(report.to_markdown(data, findings, ai_text, regions))
        con.print(f"[green]Report written to {a.output}[/]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
