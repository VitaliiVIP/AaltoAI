"""Paths, model ids and version strings. Everything here is frozen per run so
profiles and decisions are replayable; never use datetime.now() for date math."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
CV_TEXT_DIR = DATA_DIR / "cv_text"
# Uploaded PDFs and their first-page thumbnails, served back by the API. The
# demo pool's files live in the frontend image instead (public/assets/cvs).
UPLOADS_DIR = DATA_DIR / "uploads"
PROFILE_CACHE_DIR = DATA_DIR / "profiles"
SYNTH_DIR = DATA_DIR / "synth"
AUDIT_LOG_PATH = DATA_DIR / "audit.jsonl"

TAXONOMY_PATH = PACKAGE_DIR / "taxonomy" / "core.json"
MANIFEST_DIR = PACKAGE_DIR / "manifests"
# Jobs the HR editor writes go under DATA_DIR, which is the only tree mounted as a
# volume in the container — anything written into the package would be lost on the
# next image build. JOB_SEED_DIR ships the read-only defaults and is the fallback.
JOB_SEED_DIR = PACKAGE_DIR / "jobs"
JOBS_DIR = DATA_DIR / "jobs"

load_dotenv(BACKEND_DIR / ".env")

MODEL_ID = "claude-opus-5"
AS_OF = "2026-09-19"  # all date math is relative to this, never the wall clock

# Version stamps written into profiles and audit records.
SCHEMA_VERSION = "1.0"
TAXONOMY_VERSION = "core-0.2"
EXTRACT_PROMPT_VERSION = "extract-v2"
EXPLAIN_PROMPT_VERSION = "explain-v1"
SCORER_VERSION = "scorer-v1"
SOLVER_VERSION = "cpsat-v1"
