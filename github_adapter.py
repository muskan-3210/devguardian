"""All GitHub API interactions: webhook verification, PR diff fetch,
inline review comments and merge blocking via commit status.

With no GITHUB_TOKEN configured the adapter runs in mock mode: diffs come
from the bundled demo fixtures and comment posting is logged, so the full
pipeline is demo-able without a real repository.
"""
import hashlib
import hmac
import logging
from pathlib import Path

import requests

import config

logger = logging.getLogger("devguardian.github")

API = "https://api.github.com"
FIXTURES = Path(__file__).parent / "demo_fixtures"


def _headers(token: str | None = None) -> dict:
    return {
        "Authorization": f"Bearer {token or config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def verify_signature(payload: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256 against the shared webhook secret."""
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        config.GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def get_pr_diff(owner: str, repo: str, pr_number: int) -> str:
    """Fetch the unified diff for a PR."""
    if config.MOCK_GITHUB:
        fixture = FIXTURES / "sample_pr.diff"
        return fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    resp = requests.get(
        f"{API}/repos/{owner}/{repo}/pulls/{pr_number}",
        headers={**_headers(), "Accept": "application/vnd.github.diff"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def post_review(owner: str, repo: str, pr_number: int, commit_sha: str,
                summary: str, findings: list[dict], verdict: str) -> None:
    """Post one PR review containing inline comments on the buggy lines."""
    if config.MOCK_GITHUB:
        logger.info("[mock github] review on PR #%s (%s): %s inline comments",
                    pr_number, verdict, len(findings))
        return
    comments = [
        {
            "path": f["file"],
            "line": max(1, int(f.get("line", 1))),
            "side": "RIGHT",
            "body": (f"**{f['severity']} — {f['title']}**\n\n{f['detail']}\n\n"
                     f"**Suggested fix:** {f.get('suggested_fix', 'see detail')}\n\n"
                     "_— DevGuardian AI review_"),
        }
        for f in findings if f.get("file") and f.get("file") != "unknown"
    ]
    event = {"approve": "APPROVE", "comment": "COMMENT",
             "request_changes": "REQUEST_CHANGES", "block": "REQUEST_CHANGES"}[verdict]
    resp = requests.post(
        f"{API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
        headers=_headers(),
        json={"commit_id": commit_sha, "body": summary, "event": event,
              "comments": comments},
        timeout=30,
    )
    if resp.status_code == 422 and comments:
        # Some lines may fall outside the diff hunks — retry without inline anchors.
        body = summary + "\n\n" + "\n".join(
            f"- **{c['path']}:{c['line']}** {c['body'].splitlines()[0]}" for c in comments)
        requests.post(
            f"{API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=_headers(),
            json={"commit_id": commit_sha, "body": body, "event": event},
            timeout=30,
        ).raise_for_status()
    else:
        resp.raise_for_status()


def set_commit_status(owner: str, repo: str, sha: str, state: str,
                      description: str) -> None:
    """Block or allow merge via commit status (state: success|failure|pending)."""
    if config.MOCK_GITHUB:
        logger.info("[mock github] status %s on %s: %s", state, sha[:8], description)
        return
    requests.post(
        f"{API}/repos/{owner}/{repo}/statuses/{sha}",
        headers=_headers(),
        json={"state": state, "description": description[:140],
              "context": "devguardian/trust-gate"},
        timeout=30,
    ).raise_for_status()


def parse_pr_event(payload: dict) -> dict | None:
    """Extract the fields the pipeline needs from a pull_request webhook payload."""
    if "pull_request" not in payload:
        return None
    pr = payload["pull_request"]
    return {
        "action": payload.get("action"),
        "number": pr["number"],
        "title": pr.get("title", ""),
        "author": pr["user"]["login"],
        "head_sha": pr["head"]["sha"],
        "repo_owner": payload["repository"]["owner"]["login"],
        "repo_name": payload["repository"]["name"],
        "repo_full": payload["repository"]["full_name"],
    }
