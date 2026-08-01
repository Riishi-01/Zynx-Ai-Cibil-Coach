"""Configuration and constants for the CIBIL Credit Coach."""

import os
from datetime import date
from pathlib import Path

# Load .env if present
if (Path(__file__).parent.parent / ".env").exists():
    from dotenv import load_dotenv
    load_dotenv()

# ============================================================================
# WORKFLOW CONSTANTS (must be set before any computation)
# Source: build_docs/precompute_list.md §0
# ============================================================================

AS_OF_DATE = date(2026, 7, 25)  # Anchor for all time-windowed facts

CIBIL_SCORE_MIN = 300
CIBIL_SCORE_MAX = 900

CIBIL_BANDS = {
    "Poor": (300, 579),
    "Fair": (580, 699),
    "Good": (700, 749),
    "Very Good": (750, 799),
    "Excellent": (800, 900),
}

# Hysteresis: prevents label flicker at thresholds
HYSTERESIS_UTILIZATION = 0.02  # 2% utilization points
HYSTERESIS_SCORE_POINTS = 5  # 5 score points

# Regulatory & regulatory thresholds
FCRA_REPORTING_YEARS = 7  # Indian CICRA (2005) — collections fall off after 7 years
DISPUTE_MIN_AGE_YEARS = 1  # Collections older than this are easier to dispute
THIN_FILE_AGE_YEARS = 2
EXTREME_THIN_FILE_AGE_YEARS = 1

# DTI thresholds (RBI regulatory)
RBI_HIGH_DTI = 0.36  # High DTI threshold
RBI_SEVERE_DTI = 0.50  # Severe over-leverage threshold

# Utilization thresholds
MAXED_OUT_UTILIZATION = 0.90  # Above this = maxed out

# PAN validation
PAN_FORMAT_REGEX = r"^[A-Z]{5}\d{4}[A-Z]$"
PAN_INDIVIDUAL_CHAR = "P"  # 4th character for individuals

# Data
DATA_STALENESS_DAYS = 7

# Paths
# The KB fixture lives in Frontend_docs/. The customer fixture (cibil_data.json)
# is no longer required at runtime — customers are read from SQLite. It is only
# consulted by scripts/seed_db.py when re-seeding from scratch.
DATA_DIR = Path(__file__).parent.parent / "Frontend_docs"
CIBIL_DATA_PATH = Path(__file__).parent.parent / "build_docs" / "cibil_data.json"
LABEL_KB_PATH = DATA_DIR / "label_kb.json"

# LLM
# Pinned to a specific snapshot id so the chat RAG metadata footer shows
# the exact model the response came from. ``OPENAI_MODEL`` remains
# overridable via env for ops rollouts / A-B tests.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini-2024-07-18")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1100"))

# LangSmith (optional)
LANGSMITH_ENABLED = bool(os.getenv("LANGSMITH_API_KEY"))
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "cibil-coach")
