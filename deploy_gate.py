"""Module 6 — Deployment Risk Gate.

Aggregates the trust scores of every author in a release plus unresolved
HIGH/CRITICAL findings into a Red/Yellow/Green gate decision. Designed to
run as the final check in an Azure/GitHub pipeline before deploy.
"""
import logging

import nim_client
import notifier
from database import get_db

logger = logging.getLogger("devguardian.gate")

GREEN, YELLOW, RED = "GREEN", "YELLOW", "RED"


def evaluate(release_authors: list[str] | None = None) -> dict:
    """Gate decision for a release.

    Rules:
      RED    — any author DTS < 20, or any unresolved CRITICAL finding
      YELLOW — avg DTS < 60, or unresolved HIGH findings
      GREEN  — otherwise
    """
    with get_db() as db:
        if release_authors:
            placeholders = ",".join("?" * len(release_authors))
            rows = db.execute(
                f"SELECT d.username, t.score FROM developers d "
                f"JOIN trust_scores t ON t.developer_id = d.id "
                f"WHERE t.id IN (SELECT MAX(id) FROM trust_scores GROUP BY developer_id) "
                f"AND d.username IN ({placeholders})",
                release_authors,
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT d.username, t.score FROM developers d "
                "JOIN trust_scores t ON t.developer_id = d.id "
                "WHERE t.id IN (SELECT MAX(id) FROM trust_scores GROUP BY developer_id)"
            ).fetchall()
        unresolved = db.execute(
            "SELECT severity, COUNT(*) AS n FROM security_findings "
            "WHERE resolved = 0 AND severity IN ('HIGH','CRITICAL') GROUP BY severity"
        ).fetchall()

    scores = {r["username"]: r["score"] for r in rows}
    sev = {r["severity"]: r["n"] for r in unresolved}
    avg_dts = round(sum(scores.values()) / len(scores), 1) if scores else None
    min_dts = min(scores.values()) if scores else None

    reasons = []
    status = GREEN
    if sev.get("CRITICAL"):
        status = RED
        reasons.append(f"{sev['CRITICAL']} unresolved CRITICAL security finding(s)")
    if min_dts is not None and min_dts < 20:
        status = RED
        low = [u for u, s in scores.items() if s < 20]
        reasons.append(f"{len(low)} author(s) below the trust threshold (DTS < 20)")
    if status != RED:
        if sev.get("HIGH"):
            status = YELLOW
            reasons.append(f"{sev['HIGH']} unresolved HIGH finding(s)")
        if avg_dts is not None and avg_dts < 60:
            status = YELLOW
            reasons.append(f"release average DTS is {avg_dts} (< 60)")
    if not reasons:
        reasons.append("all authors trusted and no unresolved high-risk findings")

    result = {
        "status": status,
        "avg_dts": avg_dts,
        "min_dts": min_dts,
        "authors_evaluated": len(scores),
        "unresolved_findings": sev,
        "reasons": reasons,
        "summary": nim_client.write_report(
            f"One-sentence deploy gate summary for status {status}: {'; '.join(reasons)}"
        ) or f"Deploy gate is {status}: {'; '.join(reasons)}.",
    }
    severity = {"GREEN": "success", "YELLOW": "warning", "RED": "critical"}[status]
    notifier.send_alert(f"🚦 Deployment Gate: {status}", result["summary"], severity,
                        fields=[{"name": "Avg DTS", "value": avg_dts},
                                {"name": "Authors", "value": len(scores)},
                                {"name": "Unresolved HIGH/CRIT", "value": sum(sev.values()) or 0}])
    logger.info("Deploy gate: %s (%s)", status, reasons)
    return result
