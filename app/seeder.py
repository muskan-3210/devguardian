"""Seed 4 demo developers with realistic metrics, 12 weeks of DTS history,
sample PRs, reviews and security findings — everything the dashboard and
demo flow need. Run: python -m app.seeder
"""
import json
import random
from datetime import datetime, timedelta, timezone

from . import database
from . import dts_engine
from .database import get_db

random.seed(42)  # deterministic demo data

# Metrics chosen so each persona lands in its intended DTS band under the
# official formula (max achievable score is ~80, so "shallow" starts there).
# Muskan and Yogesh are the real team members; Alex and Sam are fictional
# personas that demonstrate the standard and block bands.
DEVELOPERS = [
    # username, display, role, months_ago_joined, metrics(bug, revert, coverage, security, accept)
    # muskan-3210 and yogeshgurjar119 are REAL GitHub logins (repo owner + collaborator)
    # so live PR webhooks resolve to the intended trust band; alex/sam are demo-only personas.
    ("muskan-3210", "Muskan", "senior engineer", 30, (0.0, 0.00, 15.0, 0, 1.00)),       # 80 shallow
    ("alex-rivera", "Alex Rivera", "engineer", 14, (0.5, 0.02, 5.0, 0, 0.70)),          # 65 standard
    ("yogeshgurjar119", "Yogesh", "engineer", 5, (1.2, 0.10, -2.0, 1, 0.40)),           # 36 deep
    ("sam-iqbal", "Sam Iqbal", "junior engineer", 3, (2.4, 0.25, -6.0, 3, 0.20)),       # 0 block
]

SAMPLE_FINDINGS = [
    ("builtin.sql-injection", "CRITICAL", "app/database.py", 42,
     "SQL query built with string formatting — injection risk."),
    ("builtin.hardcoded-secret", "HIGH", "app/config.py", 7,
     "Hardcoded credential committed to source."),
    ("builtin.sql-injection", "CRITICAL", "app/users.py", 88,
     "SQL query built with string formatting — injection risk."),
    ("builtin.tls-verify-off", "HIGH", "app/client.py", 15,
     "TLS certificate verification disabled."),
    ("builtin.weak-hash", "MEDIUM", "app/auth.py", 31,
     "Weak hash algorithm used — unsuitable for passwords."),
]


def seed() -> None:
    database.init_db()
    nowdt = datetime.now(timezone.utc)

    with get_db() as db:
        # delete children before parents (FK order)
        db.execute("DELETE FROM risk_assessments")
        db.execute("DELETE FROM reviews")
        db.execute("DELETE FROM security_findings")
        db.execute("DELETE FROM trust_scores")
        db.execute("DELETE FROM developer_metrics")
        db.execute("DELETE FROM pull_requests")
        db.execute("DELETE FROM developers")

        for username, display, role, joined_months, metrics in DEVELOPERS:
            joined = (nowdt - timedelta(days=30 * joined_months)).isoformat()
            cur = db.execute(
                "INSERT INTO developers (username, display_name, role, joined_at, created_at) "
                "VALUES (?,?,?,?,?)",
                (username, display, role, joined, database.now()),
            )
            dev_id = cur.lastrowid
            bug, revert, cov, sec, accept = metrics

            # 12 weeks of history converging onto current metrics
            for week in range(12, -1, -1):
                drift = week / 12
                jitter = lambda v, d: v + (random.random() - 0.5) * d
                week_metrics = (
                    max(0, jitter(bug + drift * 0.3, 0.2)),
                    max(0, min(1, jitter(revert + drift * 0.05, 0.04))),
                    jitter(cov - drift * 2, 1.5),
                    max(0, round(jitter(sec, 0.8))),
                    max(0, min(1, jitter(accept - drift * 0.05, 0.06))),
                )
                ts = (nowdt - timedelta(weeks=week)).isoformat()
                db.execute(
                    "INSERT INTO developer_metrics (developer_id, bug_rate, revert_rate, "
                    "coverage_delta, security_count, accept_rate, window_start, window_end, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (dev_id, *week_metrics,
                     (nowdt - timedelta(weeks=week + 12)).isoformat(), ts, ts),
                )
                result = dts_engine.calculate_dts(*week_metrics)
                db.execute(
                    "INSERT INTO trust_scores (developer_id, score, depth, breakdown_json, calculated_at) "
                    "VALUES (?,?,?,?,?)",
                    (dev_id, result["dts"], result["depth"],
                     json.dumps(result["breakdown"]), ts),
                )

            # final row with the exact target metrics so the demo numbers are stable
            db.execute(
                "INSERT INTO developer_metrics (developer_id, bug_rate, revert_rate, "
                "coverage_delta, security_count, accept_rate, window_start, window_end, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (dev_id, bug, revert, cov, sec, accept,
                 (nowdt - timedelta(weeks=12)).isoformat(), database.now(), database.now()),
            )
            final = dts_engine.calculate_dts(bug, revert, cov, sec, accept)
            db.execute(
                "INSERT INTO trust_scores (developer_id, score, depth, breakdown_json, calculated_at) "
                "VALUES (?,?,?,?,?)",
                (dev_id, final["dts"], final["depth"],
                 json.dumps(final["breakdown"]), database.now()),
            )
            print(f"  {display:18s} DTS={final['dts']:3d}  depth={final['depth']}")

        # sample findings spread over the last week (for the report + heatmap)
        dev_ids = [r["id"] for r in db.execute(
            "SELECT id FROM developers ORDER BY id DESC LIMIT 3").fetchall()]
        for i, (rule, sev, file, line, msg) in enumerate(SAMPLE_FINDINGS):
            db.execute(
                "INSERT INTO security_findings (developer_id, rule_id, severity, file, line, "
                "message, explanation, resolved, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (dev_ids[i % len(dev_ids)], rule, sev, file, line, msg,
                 msg + " Flagged during AI review.", 1 if sev == "MEDIUM" else 0,
                 (nowdt - timedelta(days=i + 1)).isoformat()),
            )

    print("\nSeed complete: 4 developers, 13 weeks of DTS history, sample findings.")


if __name__ == "__main__":
    seed()
