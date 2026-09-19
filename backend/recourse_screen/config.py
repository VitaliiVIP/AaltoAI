"""Paths, model ids and version strings. Everything here is frozen per run so
profiles and decisions are replayable; never use datetime.now() for date math."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
CV_TEXT_DIR = DATA_DIR / "cv_text"
PROFILE_CACHE_DIR = DATA_DIR / "profiles"
SYNTH_DIR = DATA_DIR / "synth"
AUDIT_LOG_PATH = DATA_DIR / "audit.jsonl"

TAXONOMY_PATH = PACKAGE_DIR / "taxonomy" / "swe_core.json"
MANIFEST_DIR = PACKAGE_DIR / "manifests"
JOBS_DIR = PACKAGE_DIR / "jobs"

load_dotenv(BACKEND_DIR / ".env")

MODEL_ID = "claude-opus-5"
AS_OF = "2026-09-19"  # all date math is relative to this, never the wall clock

# Version stamps written into profiles and audit records.
SCHEMA_VERSION = "1.0"
TAXONOMY_VERSION = "swe-core-0.1"
EXTRACT_PROMPT_VERSION = "extract-v1"
EXPLAIN_PROMPT_VERSION = "explain-v1"
SCORER_VERSION = "scorer-v1"
SOLVER_VERSION = "cpsat-v1"
