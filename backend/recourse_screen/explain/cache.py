"""On-disk cache of verbalised explanations, keyed by the exact prompt.

The demo is public and long-lived, so the API must never spend a token. Every
sentence the model has ever written for a given `ExplanationInput` is kept
under `data/explanations/{sha}.json`, and `generate_explanation` reads from
here first. Only `scripts/cache_explanations.py` writes: it is the one path
allowed to call the model, and it runs by hand.

The key is the sha256 of the prompt version plus the prompt JSON -- the exact
bytes the model saw -- so any change to the deltas, the mode, the target rank
or the job version is a different entry, and a prompt rewrite starts a fresh
cache. The model id is *not* in the key: it is stored in the record and quoted
back as the explanation's `model_version`, so a later default-model bump keeps
serving what was actually generated rather than silently falling back.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import config
from ..schemas import Sentence
from .whitelist import ExplanationInput

log = logging.getLogger(__name__)

__all__ = ["cache_key", "cache_path", "load_cached", "store_cached"]


def cache_key(input: ExplanationInput) -> str:
    payload = f"{config.EXPLAIN_PROMPT_VERSION}\n{input.to_prompt_json()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_path(key: str, directory: Path | None = None) -> Path:
    return (directory or config.EXPLANATION_CACHE_DIR) / f"{key}.json"


def load_cached(
    input: ExplanationInput, *, directory: Path | None = None
) -> tuple[list[Sentence], str] | None:
    """The cached sentences and the model version that wrote them, or None."""
    path = cache_path(cache_key(input), directory)
    if not path.exists():
        return None
    try:
        record: dict[str, Any] = json.loads(path.read_text())
        sentences = [Sentence.model_validate(s) for s in record["sentences"]]
        model_version = str(record["model_version"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("unreadable explanation cache %s: %s", path, exc)
        return None
    return sentences, model_version


def store_cached(
    input: ExplanationInput,
    sentences: list[Sentence],
    *,
    model_version: str,
    directory: Path | None = None,
) -> Path:
    """Write one record. Only checked sentences belong here: the caller has
    already run them through the checker, and a reader trusts that."""
    key = cache_key(input)
    path = cache_path(key, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "key": key,
        "explain_prompt_version": config.EXPLAIN_PROMPT_VERSION,
        "model_version": model_version,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": json.loads(input.to_prompt_json()),
        "sentences": [s.model_dump() for s in sentences],
    }, indent=1, ensure_ascii=False))
    return path
