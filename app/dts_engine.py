"""Module 1 — Developer Trust Score (DTS) engine.

DTS is a 0-100 trust signal recalculated from five Azure DevOps/GitHub
signals. It is used ONLY by the AI pipeline to pick review depth — it is
never surfaced to managers and every score ships with an explainable
factor-by-factor breakdown (no black-box decisions).

Formula (from the project brief):
    DTS  = 70                      # neutral baseline
    DTS -= bug_rate * 20           # bugs per 10 merged PRs
    DTS -= revert_rate * 15        # ratio 0.0-1.0
    DTS += coverage_delta * 0.3    # avg % coverage change
    DTS -= security_count * 10     # HIGH/CRITICAL findings (90d)
    DTS += accept_rate * 5         # first-pass accept ratio 0.0-1.0
    DTS  = clamp(DTS, 0, 100)
"""
import json

from . import config
from .database import get_db, now

BASELINE = 70

WEIGHTS = {
    "bug_rate": -20,
    "revert_rate": -15,
    "coverage_delta": 0.3,
    "security_count": -10,
    "accept_rate": 5,
}


def calculate_dts(bug_rate: float, revert_rate: float, coverage_delta: float,
                  security_count: int, accept_rate: float) -> dict:
    """Compute DTS with a fully explainable breakdown."""
    contributions = {
        "baseline": BASELINE,
        "bug_rate": round(bug_rate * WEIGHTS["bug_rate"], 2),
        "revert_rate": round(revert_rate * WEIGHTS["revert_rate"], 2),
        "coverage_delta": round(coverage_delta * WEIGHTS["coverage_delta"], 2),
        "security_count": round(security_count * WEIGHTS["security_count"], 2),
        "accept_rate": round(accept_rate * WEIGHTS["accept_rate"], 2),
    }
    raw = sum(contributions.values())
    dts = max(0, min(100, round(raw)))
    return {
        "dts": dts,
        "depth": get_review_depth(dts),
        "breakdown": contributions,
        "inputs": {
            "bug_rate": bug_rate, "revert_rate": revert_rate,
            "coverage_delta": coverage_delta, "security_count": security_count,
            "accept_rate": accept_rate,
        },
    }


def get_review_depth(dts: int) -> str:
    if dts >= config.DTS_SHALLOW_MIN:
        return "shallow"
    if dts >= config.DTS_STANDARD_MIN:
        return "standard"
    if dts >= config.DTS_DEEP_MIN:
        return "deep"
    return "block"


def recalculate_developer(developer_id: int) -> dict:
    """Recalculate DTS from the developer's latest metrics row and persist it."""
    with get_db() as db:
        metrics = db.execute(
            "SELECT * FROM developer_metrics WHERE developer_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (developer_id,),
        ).fetchone()
        if metrics is None:
            raise ValueError(f"No metrics recorded for developer {developer_id}")
        result = calculate_dts(
            metrics["bug_rate"], metrics["revert_rate"], metrics["coverage_delta"],
            metrics["security_count"], metrics["accept_rate"],
        )
        db.execute(
            "INSERT INTO trust_scores (developer_id, score, depth, breakdown_json, calculated_at) "
            "VALUES (?,?,?,?,?)",
            (developer_id, result["dts"], result["depth"],
             json.dumps(result["breakdown"]), now()),
        )
    return result


def get_current_dts(username: str) -> dict | None:
    """Latest DTS + breakdown for a developer; None if unknown."""
    with get_db() as db:
        row = db.execute(
            "SELECT d.id, d.username, d.display_name, t.score, t.depth, "
            "       t.breakdown_json, t.calculated_at "
            "FROM developers d "
            "JOIN trust_scores t ON t.developer_id = d.id "
            "WHERE d.username = ? ORDER BY t.calculated_at DESC LIMIT 1",
            (username,),
        ).fetchone()
    if row is None:
        return None
    return {
        "developer_id": row["id"], "username": row["username"],
        "display_name": row["display_name"], "dts": row["score"],
        "depth": row["depth"], "breakdown": json.loads(row["breakdown_json"]),
        "calculated_at": row["calculated_at"],
    }


def get_or_default_dts(username: str) -> dict:
    """DTS for the PR author. Unknown developers get the neutral baseline
    (standard review) — new team members are neither trusted nor punished."""
    found = get_current_dts(username)
    if found:
        return found
    return {
        "developer_id": None, "username": username, "display_name": username,
        "dts": BASELINE, "depth": get_review_depth(BASELINE),
        "breakdown": {"baseline": BASELINE, "note": "new developer — neutral default"},
        "calculated_at": now(),
    }


def all_developers_with_scores() -> list[dict]:
    """Every developer with their latest score and 12-week history (dashboard)."""
    with get_db() as db:
        devs = db.execute("SELECT * FROM developers ORDER BY id").fetchall()
        out = []
        for dev in devs:
            history = db.execute(
                "SELECT score, depth, breakdown_json, calculated_at FROM trust_scores "
                "WHERE developer_id = ? ORDER BY calculated_at DESC LIMIT 12",
                (dev["id"],),
            ).fetchall()
            latest = history[0] if history else None
            out.append({
                "id": dev["id"], "username": dev["username"],
                "display_name": dev["display_name"], "role": dev["role"],
                "dts": latest["score"] if latest else None,
                "depth": latest["depth"] if latest else None,
                "breakdown": json.loads(latest["breakdown_json"]) if latest else {},
                "history": [
                    {"score": h["score"], "at": h["calculated_at"]}
                    for h in reversed(history)
                ],
            })
        return out
