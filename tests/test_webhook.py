"""Integration tests for the webhook handler and demo pipeline."""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import config, database, seeder


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(config, "MOCK_NIM", True)
    monkeypatch.setattr(config, "MOCK_GITHUB", True)
    monkeypatch.setattr(config, "MOCK_NOTIFIER", True)
    database.init_db()
    seeder.seed()
    from app.main import app
    return TestClient(app)


def _signed(payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(config.GITHUB_WEBHOOK_SECRET.encode(),
                               body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}


PR_PAYLOAD = {
    "action": "opened",
    "pull_request": {
        "number": 7, "title": "fix auth", "user": {"login": "sam-iqbal"},
        "head": {"sha": "abc123"},
    },
    "repository": {"name": "devguardian-demo", "full_name": "o/devguardian-demo",
                   "owner": {"login": "o"}},
}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_webhook_accepts_pr_event(client):
    body, headers = _signed(PR_PAYLOAD)
    resp = client.post("/webhook", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "review_started"


def test_webhook_ignores_non_pr_events(client):
    body, headers = _signed({"action": "opened", "issue": {}})
    resp = client.post("/webhook", content=body, headers=headers)
    assert resp.json()["status"] == "ignored"


def test_blocked_developer_gets_no_ai_review(client):
    resp = client.post("/api/demo/simulate?persona=sam-iqbal&scenario=buggy")
    data = resp.json()
    assert data["depth"] == "block"
    assert data["verdict"] == "block"
    assert data["findings"] == []  # no AI call for blocked PRs


def test_deep_review_finds_planted_bugs(client):
    resp = client.post("/api/demo/simulate?persona=yogeshgurjar119&scenario=buggy")
    data = resp.json()
    assert data["depth"] == "deep"
    assert data["verdict"] == "request_changes"
    severities = {f["severity"] for f in data["findings"]}
    assert "CRITICAL" in severities  # SQL injection planted in fixture
    assert data["generated_tests"], "deep review must generate missing tests"
    assert data["risk"]["security"] == "High"


def test_shallow_review_for_trusted_developer(client):
    resp = client.post("/api/demo/simulate?persona=muskan-3210&scenario=clean")
    data = resp.json()
    assert data["depth"] == "shallow"
    assert data["verdict"] == "approve"
    assert data["findings"] == []


def test_developers_api_returns_seeded_team(client):
    data = client.get("/api/developers").json()
    assert len(data["developers"]) == 4
    by_user = {d["username"]: d for d in data["developers"]}
    assert by_user["muskan-3210"]["depth"] == "shallow"
    assert by_user["sam-iqbal"]["depth"] == "block"


def test_deploy_gate_red_with_blocked_author(client):
    data = client.get("/api/deploy-gate").json()
    assert data["status"] == "RED"  # sam-iqbal (DTS 0) + unresolved CRITICAL findings


def test_weekly_report_generates(client):
    data = client.get("/api/report").json()
    assert data["aggregates"]["team_size"] == 4
    assert len(data["narrative"]) > 50
