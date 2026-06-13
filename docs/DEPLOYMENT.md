# DevGuardian — Deployment Guide

## 1. Local (zero keys — mock mode)

```bash
pip install -r requirements.txt
python -m app.seeder
uvicorn app.main:app --reload
# dashboard: http://localhost:8000/dashboard
```

No credentials required: NIM, GitHub and Discord all auto-mock when their keys are absent (`/health` shows live/mock per integration).

## 2. Going live — credentials

Copy `.env.example` → `.env` and fill:

| Variable | Where to get it |
|---|---|
| `NVIDIA_API_KEY` | build.nvidia.com → Settings → API Keys (free, phone OTP) |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → PAT (classic) — scopes `repo`, `read:user`, `write:discussion` |
| `GITHUB_WEBHOOK_SECRET` | any random string — must match the repo webhook setting |
| `GITHUB_REPO_OWNER` / `GITHUB_REPO_NAME` | your demo repo |
| `TEAMS_WEBHOOK_URL` | Discord channel → Integrations → Webhooks → Copy URL |

## 3. Webhook tunnel (live demo)

```bash
ngrok config add-authtoken <YOUR_TOKEN>
ngrok http 8000
```

GitHub repo → Settings → Webhooks → Add webhook:
- Payload URL: `https://<ngrok-id>.ngrok.io/webhook`
- Content type: `application/json`
- Secret: value of `GITHUB_WEBHOOK_SECRET`
- Events: *Pull requests* only

## 4. Docker

```bash
docker compose up --build
```

Data (SQLite + ChromaDB) persists in the `devguardian-data` volume. The container **seeds demo data on first start** (via `entrypoint.sh`, after the volume mounts) and exposes a healthcheck on `/health`.

## 5. Render (Docker, free tier)

A `render.yaml` blueprint is included, so the service is one-click:

1. Push the repo to GitHub.
2. Render → **New → Blueprint** → pick the repo (it reads `render.yaml`), **or** New → Web Service → Docker.
3. In the service's **Environment**, set the secrets you want live (`NVIDIA_API_KEY`, `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `TEAMS_WEBHOOK_URL`, `GITHUB_REPO_OWNER`, `GITHUB_REPO_NAME`). Any left unset stays in **mock mode** — the app still boots.
4. Render injects `$PORT`; `entrypoint.sh` binds `0.0.0.0:$PORT` and seeds on first start. Health check path is `/health`.
5. Use the generated `https://<app>.onrender.com/webhook` as the GitHub webhook target — **no ngrok needed**.

**Notes for Render:**
- **Memory:** ChromaDB pulls in `onnxruntime`; the free 512 MB instance works but cold-starts slowly. The `starter` plan is smoother for a live demo.
- **Persistence:** free instances have ephemeral disk, so the DB + DNA store **re-seed on each restart** (fine for a demo). For durable data, switch to a paid plan and attach the disk block shown (commented) in `render.yaml`, setting `DATABASE_PATH=/data/devguardian.db` and `CHROMA_PATH=/data/.chroma`.
- **Build size/time:** `semgrep` is the heaviest dependency. The scanner falls back to a built-in OWASP rule pack when Semgrep is absent, so you can drop `semgrep` from `requirements.txt` for a much faster, lighter Render build with no loss of demo functionality.
- **Secrets:** `.env` is git-ignored and is **not** deployed; Render reads the dashboard env vars via `os.getenv` (the app calls `load_dotenv` only if a local `.env` exists).

## 6. Operations

- **Backup**: copy `devguardian.db` and the `.chroma/` directory (both are plain files); in Docker, snapshot the `devguardian-data` volume.
- **Logs**: structured stdout (`uvicorn` + module loggers); audit trail queryable at `/api/audit`.
- **Weekly jobs**: schedule `GET /api/report?post=true` via GitHub Actions cron (free 2000 min/month):

```yaml
on:
  schedule: [{cron: "0 9 * * 1"}]
jobs:
  weekly-report:
    runs-on: ubuntu-latest
    steps:
      - run: curl -fsS "https://<your-app>/api/report?post=true"
```

- **Rate limits**: NIM free tier ≈ 40 req/min shared; `nim_client.py` retries and falls back to `nvidia/nemotron-super-49b-instruct` on 429.
