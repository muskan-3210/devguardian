"""Central configuration for DevGuardian.

Every integration degrades gracefully: if its key is missing the module runs
in MOCK MODE so the full pipeline stays demo-able with zero credentials.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Credentials -----------------------------------------------------------
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_TOKEN_YOGESH = os.getenv("GITHUB_TOKEN_YOGESH", "").strip()
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "devguardian2026")
GITHUB_REPO_OWNER = os.getenv("GITHUB_REPO_OWNER", "your-github-username")
GITHUB_REPO_NAME = os.getenv("GITHUB_REPO_NAME", "devguardian-demo")
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "").strip()

# --- Storage ---------------------------------------------------------------
DATABASE_PATH = str(BASE_DIR / os.getenv("DATABASE_PATH", "devguardian.db"))
CHROMA_PATH = str(BASE_DIR / os.getenv("CHROMA_PATH", ".chroma"))

# --- Server ----------------------------------------------------------------
PORT = int(os.getenv("PORT", "8000"))

# --- Mock-mode flags (auto-derived, never set manually) ---------------------
MOCK_NIM = not NVIDIA_API_KEY
MOCK_GITHUB = not GITHUB_TOKEN
MOCK_NOTIFIER = not TEAMS_WEBHOOK_URL

# --- NVIDIA NIM ------------------------------------------------------------
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NIM_EMBED_URL = "https://integrate.api.nvidia.com/v1/embeddings"

# Model routing per DTS review depth (verified free models, June 2026)
MODEL_SHALLOW = "meta/llama-4-maverick"
MODEL_STANDARD = "mistralai/devstral-2-123b"
MODEL_DEEP = "qwen/qwen3-coder-480b-instruct"
MODEL_FALLBACK = "nvidia/nemotron-super-49b-instruct"
MODEL_EMBED = "nvidia/nv-embedqa-e5-v5"
MODEL_REPORT = "meta/llama-4-maverick"

# --- DTS thresholds ----------------------------------------------------------
DTS_SHALLOW_MIN = 80   # 80-100 -> shallow scan (~8s)
DTS_STANDARD_MIN = 50  # 50-79  -> standard review (~25s)
DTS_DEEP_MIN = 20      # 20-49  -> deep audit + test gen (~45s)
                       # 0-19   -> block PR, notify team lead


def integration_status() -> dict:
    """Live/mock status of each external integration — shown on the dashboard."""
    return {
        "nvidia_nim": "live" if not MOCK_NIM else "mock",
        "github": "live" if not MOCK_GITHUB else "mock",
        "notifier": "live" if not MOCK_NOTIFIER else "mock",
    }
