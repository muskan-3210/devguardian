"""DevGuardian — FastAPI orchestrator.

Endpoints:
    POST /webhook              GitHub PR webhook (signature-verified)
    GET  /dashboard            SPA dashboard
    GET  /health               liveness + integration status
    GET  /api/developers       all developers + DTS history
    GET  /api/reviews          recent AI reviews
    GET  /api/findings         security findings
    GET  /api/dna/profile      learned codebase DNA traits
    POST /api/dna/ingest       (re)build DNA store from demo history
    GET  /api/report           weekly team risk report
    GET  /api/deploy-gate      Red/Yellow/Green release gate
    POST /api/demo/simulate    run the full pipeline on a bundled demo PR
"""
import json
import logging
import time
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

import config
import database
import deploy_gate
import dna_engine
import dts_engine
import github_adapter
import notifier
import risk_reporter
import security_scanner
import test_generator
from database import get_db, now

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("devguardian")

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init_db()
    logger.info("DevGuardian started — integrations: %s", config.integration_status())
    yield


app = FastAPI(
    title="DevGuardian",
    description="AI-Powered Intelligent CI/CD Guardian — Developer Trust Score "
                "+ Codebase DNA Fingerprinting",
    version="1.0.0",
    lifespan=lifespan,
)

STATIC = Path(__file__).parent / "static"
FIXTURES = Path(__file__).parent / "demo_fixtures"


# --------------------------------------------------------------------------
# Core pipeline: webhook -> context -> DTS routing -> AI review -> actions
# --------------------------------------------------------------------------

def run_review_pipeline(author: str, title: str, diff: str,
                        repo: str = "demo", pr_number: int | str = "demo",
                        head_sha: str = "", owner: str = "") -> dict:
    """The full Layer 2/3 pipeline for one PR. Returns the complete result."""
    start = time.monotonic()
    import nim_client  # late import keeps startup fast

    # Layer 2B — trust lookup + depth routing
    trust = dts_engine.get_or_default_dts(author)
    depth = trust["depth"]
    database.audit("pipeline", "pr_received",
                   {"author": author, "dts": trust["dts"], "depth": depth, "pr": str(pr_number)})

    with get_db() as db:
        cur = db.execute(
            "INSERT INTO pull_requests (external_id, repo, title, author_id, status, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (str(pr_number), repo, title, trust["developer_id"],
             "blocked" if depth == "block" else "open", now()),
        )
        pr_id = cur.lastrowid

    # DTS 0-19 — block immediately, no AI call
    if depth == "block":
        notifier.notify_blocked_pr(author, trust["dts"], title, repo)
        if head_sha:
            github_adapter.set_commit_status(
                owner, repo, head_sha, "failure",
                f"Blocked: author trust score {trust['dts']} < {config.DTS_DEEP_MIN}")
        return {
            "pr_id": pr_id, "author": author, "dts": trust["dts"], "depth": depth,
            "verdict": "block", "summary": "PR blocked — team lead review required.",
            "trust_breakdown": trust["breakdown"], "findings": [],
            "dna_violations": [], "generated_tests": {}, "risk": None,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }

    # Layer 2C — adaptive AI review
    review = nim_client.review_pr(diff, depth)

    # Layer 2D — DNA fingerprint check (standard + deep)
    files = security_scanner.files_from_diff(diff)
    dna_violations = []
    if depth in ("standard", "deep"):
        dna_violations = dna_engine.check_violations(repo, files)

    # Module 3 — security scan (deep always; standard when AI found issues)
    sec_findings = []
    if depth == "deep" or (depth == "standard" and review["findings"]):
        sec_findings = security_scanner.scan_diff(diff, pr_id, trust["developer_id"])

    # Module 4 — test gap detection + generation (deep only)
    generated_tests = {}
    if depth == "deep":
        generated_tests = test_generator.generate_missing_tests(files)

    # Risk classification (explainable, threshold-based)
    risk = _classify_risk(review["findings"], sec_findings, dna_violations, generated_tests)

    # Layer 3 — actions
    all_findings = review["findings"] + [
        {"file": f["file"], "line": f["line"], "severity": f["severity"],
         "title": f["message"], "detail": f["explanation"],
         "suggested_fix": "See explanation."} for f in sec_findings
    ]
    verdict = review["verdict"]
    if any(f.get("severity") in ("HIGH", "CRITICAL") for f in all_findings):
        verdict = "request_changes"
        notifier.notify_high_risk(author, title, all_findings)
    if head_sha:
        github_adapter.post_review(owner, repo, int(pr_number), head_sha,
                                   review["summary"], all_findings, verdict)
        github_adapter.set_commit_status(
            owner, repo, head_sha,
            "failure" if verdict == "request_changes" else "success",
            f"DevGuardian {depth} review: {len(all_findings)} finding(s)")

    duration_ms = int((time.monotonic() - start) * 1000)
    with get_db() as db:
        db.execute(
            "INSERT INTO reviews (pr_id, depth, model, verdict, findings_json, duration_ms, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (pr_id, depth, review["model"], verdict,
             json.dumps(all_findings), duration_ms, now()),
        )
        db.execute(
            "INSERT INTO risk_assessments (pr_id, bug_risk, security_risk, "
            "maintainability_risk, deployment_risk, explanation, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (pr_id, risk["bug"], risk["security"], risk["maintainability"],
             risk["deployment"], risk["explanation"], now()),
        )

    return {
        "pr_id": pr_id, "author": author, "dts": trust["dts"], "depth": depth,
        "model": review["model"], "verdict": verdict, "summary": review["summary"],
        "trust_breakdown": trust["breakdown"], "findings": all_findings,
        "dna_violations": dna_violations,
        "generated_tests": generated_tests, "risk": risk, "duration_ms": duration_ms,
    }


def _classify_risk(ai_findings: list, sec_findings: list,
                   dna_violations: list, test_gaps: dict) -> dict:
    """Explainable Low/Medium/High risk classification per dimension."""
    crit = sum(1 for f in ai_findings + sec_findings if f.get("severity") == "CRITICAL")
    high = sum(1 for f in ai_findings + sec_findings if f.get("severity") == "HIGH")

    def level(score: int) -> str:
        return "High" if score >= 2 else "Medium" if score == 1 else "Low"

    bug = level(min(2, len(ai_findings) // 2 + crit))
    security = level(2 if crit else 1 if high else 0)
    maintainability = level(min(2, len(dna_violations)))
    deployment = level(2 if crit else 1 if (high or test_gaps) else 0)
    explanation = (
        f"{crit} critical and {high} high finding(s); {len(dna_violations)} DNA "
        f"violation(s); {len(test_gaps)} file(s) with untested functions."
    )
    return {"bug": bug, "security": security, "maintainability": maintainability,
            "deployment": deployment, "explanation": explanation}


# --------------------------------------------------------------------------
# Webhook + health
# --------------------------------------------------------------------------

@app.post("/webhook")
async def github_webhook(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not config.MOCK_GITHUB:
        if not github_adapter.verify_signature(
                body, request.headers.get("X-Hub-Signature-256")):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    payload = json.loads(body or "{}")
    event = github_adapter.parse_pr_event(payload)
    if event is None or event["action"] not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored"}

    diff = github_adapter.get_pr_diff(event["repo_owner"], event["repo_name"],
                                      event["number"])
    background.add_task(
        run_review_pipeline, event["author"], event["title"], diff,
        event["repo_name"], event["number"], event["head_sha"], event["repo_owner"],
    )
    return {"status": "review_started", "pr": event["number"]}


@app.get("/health")
def health():
    return {"status": "ok", "integrations": config.integration_status()}


# --------------------------------------------------------------------------
# Dashboard + REST API
# --------------------------------------------------------------------------

@app.get("/")
@app.get("/dashboard")
def dashboard():
    return FileResponse(STATIC / "index.html")


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    return FileResponse(STATIC / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/developers")
def api_developers():
    return {"developers": dts_engine.all_developers_with_scores(),
            "integrations": config.integration_status()}


@app.get("/api/reviews")
def api_reviews(limit: int = 25):
    with get_db() as db:
        rows = db.execute(
            "SELECT r.*, p.title, p.repo, d.display_name AS author "
            "FROM reviews r "
            "LEFT JOIN pull_requests p ON p.id = r.pr_id "
            "LEFT JOIN developers d ON d.id = p.author_id "
            "ORDER BY r.created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return {"reviews": [
        {**dict(r), "findings": json.loads(r["findings_json"])} for r in rows
    ]}


@app.get("/api/findings")
def api_findings(limit: int = 100):
    with get_db() as db:
        rows = db.execute(
            "SELECT f.*, d.display_name AS author FROM security_findings f "
            "LEFT JOIN developers d ON d.id = f.developer_id "
            "ORDER BY f.created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return {"findings": [dict(r) for r in rows]}


@app.get("/api/dna/profile")
def api_dna_profile(repo: str = "demo"):
    profile = dna_engine.get_profile(repo)
    if profile is None:
        raise HTTPException(status_code=404,
                            detail="No DNA profile yet — POST /api/dna/ingest first")
    return profile


@app.post("/api/dna/ingest")
def api_dna_ingest(repo: str = "demo"):
    history_dir = FIXTURES / "history"
    files = {p.name: p.read_text(encoding="utf-8")
             for p in history_dir.glob("*.py")}
    if not files:
        raise HTTPException(status_code=404, detail="No history fixtures found")
    return dna_engine.ingest_history(repo, files)


@app.get("/api/report")
def api_report(days: int = 7, post: bool = False):
    return risk_reporter.generate_report(days, post=post)


@app.get("/api/deploy-gate")
def api_deploy_gate(authors: str | None = None):
    author_list = [a.strip() for a in authors.split(",")] if authors else None
    return deploy_gate.evaluate(author_list)


@app.get("/api/audit")
def api_audit(limit: int = 50):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return {"logs": [dict(r) for r in rows]}


# --------------------------------------------------------------------------
# Demo simulation — full pipeline without GitHub
# --------------------------------------------------------------------------

@app.post("/api/demo/simulate")
def api_demo_simulate(persona: str = "rahul-verma", scenario: str = "buggy"):
    """Run the complete pipeline on a bundled demo diff.

    persona:  any seeded username (rahul-verma = block, james-okafor = deep,
              elena-petrova = standard, priya-sharma = shallow)
    scenario: buggy | clean
    """
    fixture = FIXTURES / ("sample_pr.diff" if scenario == "buggy" else "clean_pr.diff")
    if not fixture.exists():
        raise HTTPException(status_code=404, detail="Demo fixture missing")
    title = ("fix: update auth handling" if scenario == "buggy"
             else "feat: add uptime metrics with tests")
    result = run_review_pipeline(persona, title, fixture.read_text(encoding="utf-8"))
    return JSONResponse(result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=True)
