"""Pass A: one Claude call per CV, then deterministic post-processing.

Two caches, keyed by the sha256 of the CV *text*:

- `data/profiles_raw/{sha}.json` - the raw model output plus the CV text and the version
  stamps of the run. Post-processing can be re-run from here for free, which matters
  because the arithmetic and the evidence policy change far more often than the prompt.
- `config.PROFILE_CACHE_DIR/{sha}.json` - the finished `Profile`.

There is no verify pass and no self-consistency sampling here; both are described in the
design brief as later additions and neither is needed for the demo corpus.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .. import config  # noqa: F401  - imported for its load_dotenv side effect
from ..loaders import load_manifest, load_taxonomy, save_profile
from ..schemas import Manifest, Profile, Provenance
from . import prompts
from .pdf import load_cv_text, sha256_text
from .postprocess import build_profile, pii_warnings, verification_stats

log = logging.getLogger(__name__)

RAW_CACHE_DIR: Path = config.DATA_DIR / "profiles_raw"
DEFAULT_MANIFEST = "software_engineering.json"
MAX_TOKENS = 16000
EFFORT = "medium"

__all__ = [
    "ExtractionError",
    "RAW_CACHE_DIR",
    "extract_file",
    "extract_profile",
    "extract_raw",
    "load_raw_cache",
    "profile_cache_path",
    "raw_cache_path",
    "reprocess_cached",
]


class ExtractionError(RuntimeError):
    """The model refused, or the API call failed in a way retrying will not fix."""


_client: Any = None


def _get_client() -> Any:
    """Lazily build the Anthropic client so importing this module needs no API key."""
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()
    return _client


def raw_cache_path(sha: str) -> Path:
    return RAW_CACHE_DIR / f"{sha}.json"


def profile_cache_path(sha: str) -> Path:
    return config.PROFILE_CACHE_DIR / f"{sha}.json"


# --------------------------------------------------------------------------- #
# The LLM call
# --------------------------------------------------------------------------- #

def extract_raw(cv_text: str, *, taxonomy=None) -> BaseModel:
    """One structured-output call. Returns a validated `ExtractionOutput` instance."""
    import anthropic

    tax = taxonomy or load_taxonomy()
    output_model = prompts.extraction_model_for(tax)
    system_prompt = prompts.build_system_prompt(tax)
    client = _get_client()

    try:
        response = client.messages.parse(
            model=config.MODEL_ID,
            max_tokens=MAX_TOKENS,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompts.build_user_message(cv_text)}],
            output_format=output_model,
            output_config={"effort": EFFORT},
        )
    except anthropic.RateLimitError as exc:
        raise ExtractionError(f"rate limited after SDK retries: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise ExtractionError(f"API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ExtractionError(f"could not reach the API: {exc}") from exc

    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise ExtractionError(
            "the model refused to extract this CV "
            f"(category={getattr(details, 'category', None)!r}); route it to human review"
        )
    if response.stop_reason == "max_tokens":
        raise ExtractionError(
            f"output hit max_tokens ({MAX_TOKENS}); the profile would be truncated"
        )

    usage = response.usage
    log.debug(
        "extract: in=%s cache_read=%s cache_write=%s out=%s",
        usage.input_tokens, usage.cache_read_input_tokens,
        usage.cache_creation_input_tokens, usage.output_tokens,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise ExtractionError("structured output came back empty")
    return parsed


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #

def _write_raw_cache(sha: str, cv_text: str, raw: BaseModel, source_file: str | None,
                     extracted_at: str) -> None:
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw_cache_path(sha).write_text(json.dumps({
        "cv_sha256": sha,
        "source_file": source_file,
        "extractor_model": config.MODEL_ID,
        "prompt_version": config.EXTRACT_PROMPT_VERSION,
        "taxonomy_version": config.TAXONOMY_VERSION,
        "extracted_at": extracted_at,
        "cv_text": cv_text,
        "output": raw.model_dump(mode="json"),
    }, indent=1, ensure_ascii=False))


def load_raw_cache(sha: str) -> dict[str, Any] | None:
    path = raw_cache_path(sha)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("unreadable raw cache %s: %s", path, exc)
        return None


def _profile_from_record(record: dict[str, Any], *, manifest: Manifest) -> Profile:
    tax = load_taxonomy()
    raw = prompts.extraction_model_for(tax).model_validate(record["output"])
    provenance = Provenance(
        cv_sha256=record["cv_sha256"],
        source_file=record.get("source_file"),
        extractor_model=record.get("extractor_model", config.MODEL_ID),
        prompt_version=record.get("prompt_version", config.EXTRACT_PROMPT_VERSION),
        taxonomy_version=record.get("taxonomy_version", config.TAXONOMY_VERSION),
        extracted_at=record["extracted_at"],
    )
    return build_profile(
        raw,
        record["cv_text"],
        as_of=config.AS_OF,
        manifest=manifest,
        taxonomy=tax,
        provenance=provenance,
    )


def reprocess_cached(sha: str, *, manifest: Manifest | None = None,
                     save: bool = True) -> Profile:
    """Re-run post-processing on a cached raw extraction. No API call, no cost."""
    record = load_raw_cache(sha)
    if record is None:
        raise ExtractionError(f"no raw extraction cached for {sha}")
    mf = manifest or load_manifest(DEFAULT_MANIFEST)
    profile = _profile_from_record(record, manifest=mf)
    if save:
        save_profile(profile, profile_cache_path(sha))
    return profile


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def extract_profile(
    cv_text: str,
    *,
    source_file: str | None = None,
    use_cache: bool = True,
    manifest: Manifest | None = None,
) -> Profile:
    """CV text -> validated `Profile`.

    With `use_cache` the raw model output is reused when it exists, so post-processing
    changes can be re-run across the whole corpus without paying for extraction again.
    Post-processing always runs: the cached artefact is the model's answer, not ours.
    """
    sha = sha256_text(cv_text)
    mf = manifest or load_manifest(DEFAULT_MANIFEST)
    basename = Path(source_file).name if source_file else None

    record = load_raw_cache(sha) if use_cache else None
    if record is None:
        raw = extract_raw(cv_text)
        extracted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_raw_cache(sha, cv_text, raw, basename, extracted_at)
        record = load_raw_cache(sha)
        assert record is not None
    elif basename and record.get("source_file") != basename:
        record["source_file"] = basename

    profile = _profile_from_record(record, manifest=mf)
    save_profile(profile, profile_cache_path(sha))

    stats = verification_stats(profile)
    if stats["total"] and stats["rate"] < 1.0:
        log.info("evidence verification %s/%s for %s",
                 stats["verified"], stats["total"], basename or sha[:8])
    for warning in pii_warnings(profile):
        log.warning("%s: %s", basename or sha[:8], warning)
    return profile


def extract_file(path: str | Path, *, use_cache: bool = True,
                 manifest: Manifest | None = None) -> Profile:
    """Convenience wrapper: read a .txt or .pdf CV from disk and extract it."""
    p = Path(path)
    return extract_profile(load_cv_text(p), source_file=p.name,
                           use_cache=use_cache, manifest=manifest)
