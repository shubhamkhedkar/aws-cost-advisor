import datetime as dt
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from .rules import total_savings

USD_INR = 84  # approximate
SEV_STYLE = {"high": "bold red", "medium": "yellow", "low": "cyan", "info": "dim"}


def _money(v):
    return "-" if v is None else f"${v:.2f} (~₹{v * USD_INR:.0f})"


def print_terminal(data, findings, ai_text, regions, console=None):
    c = console or Console()
    c.print(Panel.fit(f"[bold]AWS Cost Advisor[/] — read-only scan of {', '.join(regions)}"))
    ce = data.get("cost_explorer")
    if ce:
        t = Table(title=f"Last 30 days cost ({ce['period']}) — total {ce['total']} {ce['unit']}")
        t.add_column("Service"); t.add_column("Cost", justify="right")
        for s in ce["by_service"][:10]:
            t.add_row(s["service"], f"{s['cost']:.2f}")
        c.print(t)
    t = Table(title=f"Findings ({len(findings)}) — est. savings {_money(total_savings(findings))}/mo")
    for col in ("Sev", "Category", "Resource", "Region", "Issue", "Recommendation", "Save/mo"):
        t.add_column(col, overflow="fold")
    for f in findings:
        t.add_row(f"[{SEV_STYLE[f['severity']]}]{f['severity']}[/]", f["category"], str(f["resource"]),
                  f["region"], f["issue"], f["recommendation"], _money(f["est_monthly_savings_usd"]))
    c.print(t if findings else "[green]No rule-based findings. Nice and lean![/]")
    if ai_text:
        c.print(Panel(Markdown(ai_text), title="AI recommendations"))
    if data["errors"]:
        c.print(f"[dim]Skipped/partial ({len(data['errors'])}): " + "; ".join(data["errors"][:8]) + "[/]")
    c.print("[dim]Nothing was changed. Commands are suggestions — review before running.[/]")


def to_markdown(data, findings, ai_text, regions):
    L = [f"# AWS Cost Advisor Report", "",
         f"- Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M %Z').strip()}",
         f"- Regions: {', '.join(regions)}",
         f"- Findings: {len(findings)} | Estimated savings: **{_money(total_savings(findings))}/month**", ""]
    ce = data.get("cost_explorer")
    L += ["## Last 30 days cost by service", ""]
    if ce:
        L += [f"Period {ce['period']}, total **{ce['total']} {ce['unit']}**", "", "| Service | Cost |", "|---|---:|"]
        L += [f"| {s['service']} | {s['cost']:.2f} |" for s in ce["by_service"]]
    else:
        L.append("_Cost Explorer unavailable (permission denied or not enabled)._")
    L += ["", "## Rule-based findings", ""]
    if findings:
        L += ["| Severity | Category | Resource | Region | Issue | Recommendation | Est. savings/mo |",
              "|---|---|---|---|---|---|---:|"]
        for f in findings:
            L.append(f"| {f['severity']} | {f['category']} | `{f['resource']}` | {f['region']} | {f['issue']} | "
                     f"{f['recommendation']} | {_money(f['est_monthly_savings_usd'])} |")
        cmds = [f for f in findings if f.get("cli_hint")]
        if cmds:
            L += ["", "### Suggested commands (review first — the tool never runs these)", "", "```bash"]
            L += [f"# {f['category']} {f['resource']}: {f['recommendation']}\n{f['cli_hint']}" for f in cmds]
            L.append("```")
    else:
        L.append("No findings.")
    L += ["", "## AI recommendations", "", ai_text or "_AI step skipped (no AI_API_KEY, --no-ai, or error)._"]
    if data["errors"]:
        L += ["", "## Scan notes", ""] + [f"- {e}" for e in data["errors"]]
    L += ["", "_Prices are approximate on-demand estimates; verify with the AWS Pricing Calculator._", ""]
    return "\n".join(L)
