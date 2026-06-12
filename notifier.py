"""Discord webhook notifier (Teams-compatible alert channel).

Posts rich embeds for review alerts, deploy gates and weekly reports.
With no TEAMS_WEBHOOK_URL configured it logs the message instead, so the
pipeline never fails on a missing integration.
"""
import logging

import requests

import config
from database import audit

logger = logging.getLogger("devguardian.notifier")

SEVERITY_COLORS = {
    "info": 0x3B82F6,      # blue
    "success": 0x22C55E,   # green
    "warning": 0xF59E0B,   # amber
    "critical": 0xEF4444,  # red
}


def send_alert(title: str, message: str, severity: str = "info",
               fields: list[dict] | None = None) -> bool:
    """Send an embed to the alerts channel. Returns True if delivered."""
    payload = {
        "username": "DevGuardian",
        "embeds": [{
            "title": title,
            "description": message[:4000],
            "color": SEVERITY_COLORS.get(severity, SEVERITY_COLORS["info"]),
            "fields": [
                {"name": f["name"][:256], "value": str(f["value"])[:1024], "inline": True}
                for f in (fields or [])
            ],
            "footer": {"text": "DevGuardian — AI CI/CD Guardian"},
        }],
    }
    audit("notifier", "alert", {"title": title, "severity": severity})
    if config.MOCK_NOTIFIER:
        logger.info("[mock notifier] %s: %s", title, message)
        return True
    try:
        resp = requests.post(config.TEAMS_WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Discord webhook failed: %s", exc)
        return False


def notify_blocked_pr(username: str, dts: int, pr_title: str, repo: str) -> None:
    send_alert(
        "🚫 PR blocked by DevGuardian",
        f"A pull request was blocked because the author's trust score is below the merge threshold.",
        "critical",
        fields=[
            {"name": "Repository", "value": repo},
            {"name": "PR", "value": pr_title},
            {"name": "Author DTS", "value": f"{dts} (block < {config.DTS_DEEP_MIN})"},
            {"name": "Action", "value": "Team lead review required before merge"},
        ],
    )


def notify_high_risk(username: str, pr_title: str, findings: list[dict]) -> None:
    top = [f for f in findings if f.get("severity") in ("HIGH", "CRITICAL")][:5]
    send_alert(
        "⚠️ High-risk findings in PR",
        "\n".join(f"• **{f['severity']}** {f.get('title', f.get('message', ''))} "
                  f"({f.get('file', '?')}:{f.get('line', '?')})" for f in top)
        or "High-risk findings detected.",
        "warning",
        fields=[{"name": "PR", "value": pr_title},
                {"name": "Author", "value": username},
                {"name": "Findings", "value": len(findings)}],
    )
