"""Central configuration for DevGuardian.

Every integration degrades gracefully: if its key is missing the module runs
in MOCK MODE so the full pipeline stays demo-able with zero credentials.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # project root (one level above app/)
load_dotenv(BASE_DIR / ".env")

# --- Credentials -----------------------------------------------------------
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
# No default secret — an empty value disables live webhook verification on purpose
# (see main.github_webhook) so a known secret can never be shipped in source.
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()
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

# Model routing per DTS review depth — IDs verified callable on the live
# NVIDIA NIM catalog (integrate.api.nvidia.com) on 2026-06-13. Chosen for a
# fast/quality balance (benchmarked: maverick ~8s, 122b ~17s, 397b ~19s).
MODEL_SHALLOW = "meta/llama-4-maverick-17b-128e-instruct"   # fast quick scan (~8s)
MODEL_STANDARD = "qwen/qwen3.5-122b-a10b"                    # full review (~17s)
MODEL_DEEP = "qwen/qwen3.5-122b-a10b"                        # deep audit + tests (~17s)
MODEL_FALLBACK = "nvidia/llama-3.3-nemotron-super-49b-v1.5"  # used on rate limit
MODEL_EXPLAIN = "meta/llama-4-maverick-17b-128e-instruct"    # short finding explanations (fast)
MODEL_TESTGEN = "meta/llama-4-maverick-17b-128e-instruct"    # generated unit tests (fast)
MODEL_EMBED = "nvidia/nv-embedqa-e5-v5"                      # DNA embeddings
MODEL_REPORT = "meta/llama-4-maverick-17b-128e-instruct"     # narrative reports

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
