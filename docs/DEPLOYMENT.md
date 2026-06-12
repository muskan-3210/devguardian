# DevGuardian — Deployment Guide

## 1. Local (zero keys — mock mode)

```bash
pip install -r requirements.txt
python seeder.py
uvicorn main:app --reload
# dashboard: http://localhost:8000/dashboard
```

No credentials required: NIM, GitHub and Discord all auto-mock when their keys are absent (`/health` shows live/mock per integration).

## 2. Going live — credentials

Copy `.env.example` → `.env` and fill:

| Variable | Where to get it |
|---|---|
| `NVIDIA_API_KEY` | build.nvidia.com → Settings → API Keys (free, phone OTP) |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → PAT (classic) — scopes `repo`, `read:user`, `write:discussion` |
| `GITHUB_TOKEN_YOGESH` | same, from the second demo account |
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

Data (SQLite + ChromaDB) persists in the `devguardian-data` volume. Image seeds demo data at build time and exposes a healthcheck on `/health`.

## 5. Railway / Render (free tier)

1. Push the repo to GitHub.
2. Railway → New Project → Deploy from GitHub repo (Dockerfile detected automatically).
3. Add the `.env` variables in the service settings.
4. Use the generated public URL as the GitHub webhook target — no ngrok needed.

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
