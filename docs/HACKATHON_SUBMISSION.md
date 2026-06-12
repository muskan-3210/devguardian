# DevGuardian — Hackathon Submission Document

**Theme 06 — Production Function (AI-Powered Production) · Total cost: ₹0**

## Executive summary

DevGuardian is an AI-native quality gate for Azure DevOps / GitHub pipelines. Where every other AI reviewer treats all pull requests identically, DevGuardian maintains **per-developer trust intelligence** (Developer Trust Score) and **per-codebase style intelligence** (Codebase DNA Fingerprint), and uses both to decide *how aggressively* to inspect each change — from an 8-second shallow scan for proven engineers to a 45-second security audit with auto-generated tests for risky submissions, up to a hard merge block with team-lead escalation.

## The problem

- PRs wait 2–3 days for human review; reviewer fatigue lets security bugs through.
- Existing AI reviewers are **stateless**: no memory across PRs, same depth for everyone, generic rules that ignore the team's actual conventions.
- Nothing intelligent sits between "ready to deploy" and "deploy".

## The innovation (what judges haven't seen)

1. **Adaptive review depth via DTS** — a 0–100 score from five explainable signals (bug rate, revert rate, coverage delta, security findings, first-pass accepts) routes each PR to shallow/standard/deep review or a block. Trust earns speed; risk earns scrutiny.
2. **Codebase DNA Fingerprinting** — function-level embeddings of merged history in ChromaDB plus measurable trait profiles detect "code that doesn't look like *your* codebase", with human-readable reasons.
3. **Trust-aware CI/CD** — a Red/Yellow/Green deployment gate aggregating author trust + unresolved findings per release.
4. **Team Risk Forecasting** — weekly anonymised intelligence ("3 SQL-injection patterns this week, all from engineers who joined < 6 months ago → schedule security training").
5. **Explainable AI governance** — every score, finding and gate decision carries its full reasoning; DTS is never visible to management; all automated actions are audit-logged.

## Architecture

3-layer flow: **webhook trigger → trust-routed AI orchestration (NVIDIA NIM) + DNA check (ChromaDB) + Semgrep scan + AST test-gap detection → action engine** (inline PR comments, commit-status gate, Discord/Teams alerts, SQLite persistence). Single FastAPI deployment serving a dark-mode SPA dashboard. Full diagrams: [ARCHITECTURE.md](ARCHITECTURE.md).

## Zero-cost stack

| Layer | Tool | Cost |
|---|---|---|
| AI models | NVIDIA NIM free tier (Llama 4 Maverick, Devstral-2 123B, Qwen3 Coder 480B, NV-EmbedQA-E5) | ₹0 |
| Vector DB | ChromaDB (local) | ₹0 |
| Static analysis | Semgrep OSS + built-in OWASP pack | ₹0 |
| Storage | SQLite (WAL) | ₹0 |
| Backend / UI | FastAPI + Tailwind SPA | ₹0 |
| Alerts | Discord webhook (Teams-compatible) | ₹0 |
| Hosting / CI | Railway free tier · GitHub Actions | ₹0 |

## Engineering quality

- 28 automated tests (formula, routing boundaries, scanner, webhook E2E) — all green.
- HMAC-verified webhooks, parameterised SQL, env-only secrets, audit logging.
- Every external integration auto-degrades to a deterministic mock — the demo cannot be killed by wifi or rate limits.
- One-command Docker deploy; CI Semgrep-scans DevGuardian itself.

## Business value for Microsoft

- **Azure DevOps (10M+ users)**: every shallow-routed PR reclaims engineering hours at platform scale.
- **Release protection**: DTS-deep review catches security bugs before they enter Windows/Office release branches.
- **Copilot ecosystem**: Copilot writes code; DevGuardian guards what was written — the natural next chapter of Microsoft's AI developer story.
- **Azure SLA**: the deployment gate stops risky releases before they threaten the 99.9% commitment.

## Pitch deck skeleton (10 slides)

1. Title — "The AI that knows your developers"
2. Problem — review latency + stateless AI reviewers
3. Insight — not all PRs deserve equal scrutiny
4. DTS — formula, signals, routing table
5. Codebase DNA — your standards, not generic rules
6. Live demo (4-step contrast: deep vs shallow vs block vs gate)
7. Architecture — 3 layers, zero-cost stack
8. Ethics — explainable, anonymised, pipeline-internal
9. Microsoft fit — DevOps, Copilot, SLA
10. Ask / roadmap — PostgreSQL scale-out, Azure Marketplace listing, org-level DNA
