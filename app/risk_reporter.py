"""Module 5 — Team Risk Intelligence report.

Weekly aggregation of DTS, review and security data into an anonymised
team-level report ("3 PRs introduced SQL injection patterns — all from
engineers who joined in the last 6 months"). Written by Llama 4 via NIM
and posted to the alerts channel. Individual developers are never named.
"""
import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import nim_client
from . import notifier
from .database import get_db

logger = logging.getLogger("devguardian.risk")


def _aggregate(days: int = 7) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_db() as db:
        scores = db.execute(
            "SELECT t.score, t.depth, d.joined_at FROM trust_scores t "
            "JOIN developers d ON d.id = t.developer_id "
            "WHERE t.id IN (SELECT MAX(id) FROM trust_scores GROUP BY developer_id)"
        ).fetchall()
        findings = db.execute(
            "SELECT rule_id, severity, file FROM security_findings WHERE created_at >= ?",
            (since,),
        ).fetchall()
        reviews = db.execute(
            "SELECT depth, verdict, duration_ms FROM reviews WHERE created_at >= ?",
            (since,),
        ).fetchall()

    dts_values = [r["score"] for r in scores]
    cutoff_6m = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    return {
        "window_days": days,
        "team_size": len(scores),
        "avg_dts": round(sum(dts_values) / len(dts_values), 1) if dts_values else None,
        "dts_distribution": dict(Counter(r["depth"] for r in scores)),
        "low_trust_count": sum(1 for v in dts_values if v < 50),
        "new_joiner_low_trust": sum(
            1 for r in scores if r["score"] < 50 and r["joined_at"] >= cutoff_6m),
        "findings_total": len(findings),
        "findings_by_severity": dict(Counter(f["severity"] for f in findings)),
        "top_rules": dict(Counter(f["rule_id"] for f in findings).most_common(5)),
        "hotspot_files": dict(Counter(f["file"] for f in findings).most_common(5)),
        "reviews_total": len(reviews),
        "reviews_by_depth": dict(Counter(r["depth"] for r in reviews)),
        "avg_review_ms": round(sum(r["duration_ms"] or 0 for r in reviews) / len(reviews))
                         if reviews else None,
    }


def _mock_narrative(agg: dict) -> str:
    lines = [f"**Team Risk Intelligence — last {agg['window_days']} days**", ""]
    if agg["avg_dts"] is not None:
        lines.append(f"Average team trust score is {agg['avg_dts']}. "
                     f"{agg['low_trust_count']} engineer(s) currently route to deep review.")
    if agg["new_joiner_low_trust"]:
        lines.append(f"{agg['new_joiner_low_trust']} low-trust engineer(s) joined in the last "
                     "6 months — recommendation: schedule a security onboarding/pairing session.")
    if agg["findings_total"]:
        sev = ", ".join(f"{v} {k}" for k, v in agg["findings_by_severity"].items())
        lines.append(f"{agg['findings_total']} security finding(s) this week ({sev}).")
        if agg["top_rules"]:
            top = next(iter(agg["top_rules"]))
            lines.append(f"Most frequent pattern: `{top}` — consider a focused training session.")
        if agg["hotspot_files"]:
            hot = next(iter(agg["hotspot_files"]))
            lines.append(f"Hotspot: `{hot}` attracts repeated findings — candidate for refactor.")
    else:
        lines.append("No security findings recorded this week.")
    if agg["reviews_total"]:
        lines.append(f"{agg['reviews_total']} AI review(s) ran "
                     f"(avg {agg['avg_review_ms']}ms): {agg['reviews_by_depth']}.")
    return "\n".join(lines)


def generate_report(days: int = 7, post: bool = True) -> dict:
    """Build the weekly anonymised report; optionally post it to the channel."""
    agg = _aggregate(days)
    narrative = nim_client.write_report(
        "Write an anonymised weekly engineering risk report (max 200 words) from this "
        "data. Never name individuals. End with 2 actionable recommendations.\n\n"
        + json.dumps(agg, indent=2)
    ) or _mock_narrative(agg)
    logger.info("Weekly risk report: %d finding(s), %d review(s) over %d day(s); posted=%s",
                agg["findings_total"], agg["reviews_total"], days, post)
    if post:
        notifier.send_alert("📊 Weekly Team Risk Intelligence", narrative, "info")
    return {"aggregates": agg, "narrative": narrative}
