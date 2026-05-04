"""
Configuration for GitHub Analysis services.
Add these to your .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# OLLAMA CONFIGURATION
# ============================================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
"""Ollama server URL."""

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
"""Model to use for analysis."""

OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))
"""Request timeout in seconds."""

# ============================================================================
# GITHUB ANALYZER CONFIGURATION
# ============================================================================

GITHUB_ANALYZER_MIN_MESSAGE_LENGTH = int(
    os.getenv("GITHUB_ANALYZER_MIN_MESSAGE_LENGTH", "10")
)
"""Minimum commit message length for quality scoring."""

GITHUB_ANALYZER_MAX_MESSAGE_LENGTH = int(
    os.getenv("GITHUB_ANALYZER_MAX_MESSAGE_LENGTH", "500")
)
"""Maximum optimal commit message length."""

GITHUB_ANALYZER_BIG_BANG_THRESHOLD = int(
    os.getenv("GITHUB_ANALYZER_BIG_BANG_THRESHOLD", "500")
)
"""Threshold for large commit detection (lines added in single commit)."""

# ============================================================================
# LLM GENERATION PARAMETERS
# ============================================================================

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
"""Model temperature for analysis (0-2, lower = more consistent)."""

LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))
"""Nucleus sampling parameter."""

LLM_TOP_K = int(os.getenv("LLM_TOP_K", "40"))
"""Top-k sampling parameter."""

# ============================================================================
# LOGGING
# ============================================================================

ANALYSIS_LOG_LEVEL = os.getenv("ANALYSIS_LOG_LEVEL", "INFO")
"""Log level for analysis services."""

# ============================================================================
# GITHUB API CONFIGURATION
# ============================================================================

GITHUB_PAT = os.getenv("GITHUB_PAT", "")
"""GitHub Personal Access Token for API authentication."""

GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")
"""GitHub API base URL."""

GITHUB_API_TIMEOUT = int(os.getenv("GITHUB_API_TIMEOUT", "30"))
"""Timeout for GitHub API requests in seconds."""

GITHUB_FETCH_DAYS = int(os.getenv("GITHUB_FETCH_DAYS", "30"))
"""Default number of days to fetch commits."""

GITHUB_FETCH_PER_PAGE = int(os.getenv("GITHUB_FETCH_PER_PAGE", "100"))
"""Number of commits per page (max 100)."""

# ============================================================================
# EXAMPLE .env FILE
# ============================================================================
"""
# Ollama Configuration
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_TIMEOUT=300

# GitHub API Configuration
GITHUB_PAT=your_github_pat_here
GITHUB_API_URL=https://api.github.com
GITHUB_API_TIMEOUT=30
GITHUB_FETCH_DAYS=30
GITHUB_FETCH_PER_PAGE=100

# GitHub Analyzer
GITHUB_ANALYZER_MIN_MESSAGE_LENGTH=10
GITHUB_ANALYZER_MAX_MESSAGE_LENGTH=500
GITHUB_ANALYZER_BIG_BANG_THRESHOLD=500

# LLM Parameters
LLM_TEMPERATURE=0.3
LLM_TOP_P=0.9
LLM_TOP_K=40

# Logging
ANALYSIS_LOG_LEVEL=INFO
"""
