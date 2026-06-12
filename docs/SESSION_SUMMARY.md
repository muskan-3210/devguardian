# DevGuardian — Build Session Summary (2026-06-12)

## 1. Requirements & decisions

The project was built from two requirement PDFs in the repo root, which take
precedence over the original master prompt:

| Topic | Master prompt said | PDFs said | **Chosen** |
|---|---|---|---|
| AI models | Ollama (local) | NVIDIA NIM free tier | **NVIDIA NIM** |
| Git platform | Azure DevOps | GitHub webhooks for demo | **GitHub** |
| Database | PostgreSQL | SQLite + ChromaDB | **SQLite + ChromaDB** |
| Frontend | Next.js | Jinja2 dashboard | **Tailwind SPA served by FastAPI** (single deploy) |
| Alerts | Teams | Discord webhook (Teams-compatible) | **Discord** |
| Credentials | — | — | **None yet → automatic mock mode everywhere** |

## 2. What was built

Complete project (~35 files): 6 modules per the PDF layout —
`dts_engine.py` (trust formula + depth routing), `dna_engine.py` (ChromaDB
fingerprint + trait extraction), `security_scanner.py` (Semgrep + builtin
OWASP fallback), `test_generator.py` (AST gaps + AI tests), `risk_reporter.py`
(weekly anonymised report), `deploy_gate.py` (Red/Yellow/Green) — orchestrated
by `main.py` (HMAC-verified webhook, REST API, demo simulator), plus
`nim_client.py`, `github_adapter.py`, `notifier.py`, `database.py`,
`seeder.py`, SPA dashboard, 28 tests, Docker/compose, GitHub Actions CI,
azure-pipelines.yml, and full docs (architecture/API/deployment/demo/judge-QA/
submission).

**Verified end-to-end** (all in mock mode): deep review on the buggy fixture →
8 findings + 5 DNA violations + 2 generated test files; blocked persona → no
AI call + alert; trusted persona + clean PR → shallow approve; deploy gate → RED.

## 3. Key engineering decisions

- **Automatic mock mode**: any missing `.env` key mocks that integration; the
  entire pipeline runs offline (wifi-proof demo).
- **DTS formula caps at ~80**, so the PDF's "DTS-92" persona is unreachable.
  Kept the official formula; tuned seed metrics to land personas in exact bands.
- **Semgrep doesn't pip-install on native Windows** → platform guard in
  requirements.txt + builtin OWASP regex rule pack fallback.
- **DNA embeddings**: NIM `nv-embedqa-e5-v5` when key present, else local
  deterministic hash embedder (no downloads). 0.62 cosine threshold.
- 429 fallback chain in `nim_client.py` → `nvidia/nemotron-super-49b-instruct`.

## 4. Issues hit & fixed

1. **Seeder FK bug** — `risk_assessments`/`reviews` rows must be deleted before
   `pull_requests` (FOREIGN KEY error on second run). Fixed.
2. **`pip.exe` blocked** by Windows Application Control → always use
   `python -m pip ...` on this machine.
3. **Port 8000 conflicts** — caused by a leftover background server instance;
   resolved (stop holder or use `--port 8080`).
4. FastAPI `on_event` deprecation → migrated to lifespan handler.

## 5. Customisations requested by the user

- **Team renamed** → Muskan (DTS 80, shallow, high-trust) and Yogesh (DTS 36,
  deep) as the real members, plus fictional Alex Rivera (65, standard) and
  Sam Iqbal (0, block). All tests/docs updated; `.env` var is now
  `GITHUB_TOKEN_YOGESH`.
- **Theme** → after previews of generic + 6 Microsoft-inspired options, user
  chose **Microsoft 365 light**: white/Fluent neutrals, Segoe UI, four-square
  MS logo in header, logo colors (blue/green/amber/red) across charts and
  depth badges.
- **Favicon** → DevGuardian shield filled with the four MS-logo quadrants +
  white checkmark (`static/favicon.svg`, served at `/favicon.svg`).
- **Responsive design** → swipeable tab bar, stacked cards on phones,
  fixed-height fluid charts, full-width controls on mobile, horizontally
  scrolling findings table. Verified by screenshot at 375/768/1280 px.
- **CLAUDE.md** project-memory file created at root and git-ignored.

## 6. Current state

- 28/28 tests passing; everything runs in mock mode (no live keys yet).
- Run: `python seeder.py` (reset data) → `python -m uvicorn main:app --reload`
  → http://localhost:8000/dashboard.
- ⚠️ Git repo root is currently `D:\` (whole drive) — run `git init` inside
  `D:\DevGuardian` before pushing to GitHub.

## 7. Next steps

1. Get keys: NVIDIA_API_KEY (build.nvidia.com), 2 GitHub PATs (Muskan +
   second account), Discord webhook URL → fill `.env`.
2. Map real GitHub usernames to the `muskan`/`yogesh` database personas.
3. `ngrok http 8000` + repo webhook (secret = `GITHUB_WEBHOOK_SECRET`).
4. Demo prep: `docs/DEMO_SCRIPT.md` dry-run ×3, record backup video.
