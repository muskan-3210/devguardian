# DevGuardian — API Guide

Interactive Swagger UI: `http://localhost:8000/docs` · OpenAPI JSON: `/openapi.json`

## Webhook

### `POST /webhook`
GitHub `pull_request` webhook receiver. Requires a valid `X-Hub-Signature-256` HMAC header (secret = `GITHUB_WEBHOOK_SECRET`). Responds `{"status": "review_started"}` immediately; the review pipeline runs as a background task. Actions handled: `opened`, `synchronize`, `reopened`.

## Dashboard & health

| Method | Path | Description |
|---|---|---|
| GET | `/` or `/dashboard` | SPA dashboard |
| GET | `/health` | liveness + live/mock status per integration |

## Trust & analytics

### `GET /api/developers`
All developers with latest DTS, depth, explainable breakdown and 12-week history.

```json
{"developers": [{"username": "muskan", "dts": 80, "depth": "shallow",
  "breakdown": {"baseline": 70, "bug_rate": -0.0, "coverage_delta": 4.5, "accept_rate": 5.0},
  "history": [{"score": 76, "at": "2026-03-19T..."}]}]}
```

### `GET /api/reviews?limit=25`
Recent AI reviews with depth, model, verdict, findings and duration.

### `GET /api/findings?limit=100`
Security findings with severity, location, AI explanation and resolved flag.

### `GET /api/audit?limit=50`
Audit log of every automated action.

## DNA fingerprint

| Method | Path | Description |
|---|---|---|
| POST | `/api/dna/ingest?repo=demo` | (Re)build the DNA store from historical code |
| GET | `/api/dna/profile?repo=demo` | Learned traits + chunk count (404 until ingested) |

## Intelligence

### `GET /api/report?days=7&post=false`
Weekly anonymised Team Risk Intelligence report. `post=true` also sends it to the Discord/Teams channel. Returns `{aggregates, narrative}`.

### `GET /api/deploy-gate?authors=muskan,sam-iqbal`
Release gate. Omit `authors` to evaluate the whole team.

```json
{"status": "RED", "avg_dts": 51.0, "min_dts": 0,
 "reasons": ["2 unresolved CRITICAL security finding(s)",
             "1 author(s) below the trust threshold (DTS < 20)"]}
```

## Demo

### `POST /api/demo/simulate?persona=sam-iqbal&scenario=buggy`
Runs the complete pipeline on a bundled fixture diff without GitHub.
- `persona`: `muskan` (shallow) · `alex-rivera` (standard) · `yogesh` (deep) · `sam-iqbal` (block)
- `scenario`: `buggy` (SQL injection, hardcoded secret, eval, TLS-off) · `clean`

Returns the full pipeline result: trust breakdown, findings, DNA violations, generated tests, risk classification, duration.

## Error handling

Errors use FastAPI's standard envelope `{"detail": "..."}` with appropriate status codes (401 invalid webhook signature, 404 missing profile/fixture). Validation of query/body parameters is automatic via FastAPI/Pydantic.
