"""LLM-layer configuration. Read once at import time."""
import os
from dotenv import load_dotenv

load_dotenv()

# Vertex AI / Gemini
GCP_PROJECT  = os.getenv("GCP_PROJECT",  "chapmanvoice")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

GEMINI_MODEL_PRIMARY = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-3.1-pro-preview")
GEMINI_MODEL_TOOLS   = os.getenv("GEMINI_MODEL_TOOLS",   "gemini-3.1-pro-preview-customtools")
GEMINI_MODEL_GA      = os.getenv("GEMINI_MODEL_GA",      "gemini-2.5-pro")
GEMINI_MODEL_FAST    = os.getenv("GEMINI_MODEL_FAST",    "gemini-2.5-flash")

# Ollama (offline fallback)
OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Top-level toggle. Set to "ollama" to bypass Vertex entirely (e.g. for local dev).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

# Routing knobs
DEAD_TIER_TTL_SECONDS = int(os.getenv("DEAD_TIER_TTL_SECONDS", "600"))
MAX_RETRIES_PER_TIER  = int(os.getenv("MAX_RETRIES_PER_TIER", "1"))

# Context caching
MIN_CACHE_BYTES = int(os.getenv("MIN_CACHE_BYTES", "32768"))   # 32 KB
CACHE_TTL_SECS  = int(os.getenv("CACHE_TTL_SECS", "900"))      # 15 min
