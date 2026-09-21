"""The explanation pipeline: whitelist -> cache -> verbalise -> check -> frame.

One regeneration on a failed check, then the code-generated fallback. Never a
loop, never unchecked text on the wire. The framing is always code-owned, so
even a fully-fallen-back explanation carries the same disclosures.

The model is only ever called with `allow_live=True`, which nothing reachable
from the API passes: the public demo serves the cached sentences written by
`scripts/cache_explanations.py` and falls back to the templates otherwise.
"""
from __future__ import annotations

import anthropic

from .. import config
from ..schemas import Explanation, Decision, ImmutableBlocker, NoFeasiblePath, Route, Sentence
from . import templates
from .cache import load_cached, store_cached
from .checker import check
from .verbaliser import VerbaliserError, verbalise
from .whitelist import ExplanationInput, build_explanation_input


def explanation_model_version() -> str:
    return f"{config.EXPLAIN_PROMPT_VERSION}/{config.MODEL_ID}"


def generate_explanation(
    *,
    decision: Decision,
    routes: list[Route],
    immutable_blockers: list[ImmutableBlocker],
    no_feasible_path: NoFeasiblePath | None,
    as_of: str,
    model_version: str,
    use_llm: bool = True,
    allow_live: bool = False,
    client: anthropic.Anthropic | None = None,
) -> Explanation:
    """Build the candidate-facing explanation.

    `model_version` is the screening model version quoted to the candidate; the
    returned `Explanation.model_version` is the explanation prompt + model.

    `use_llm` asks for model-written sentences; `allow_live` is what permits
    spending a call to get them. Without it, a cache miss is a template
    explanation, not an API request.
    """
    input = build_explanation_input(
        decision=decision,
        routes=routes,
        immutable_blockers=immutable_blockers,
        no_feasible_path=no_feasible_path,
        as_of=as_of,
        model_version=model_version,
    )
    return explain_input(input, use_llm=use_llm, allow_live=allow_live, client=client)


def explain_input(
    input: ExplanationInput,
    *,
    use_llm: bool = True,
    allow_live: bool = False,
    client: anthropic.Anthropic | None = None,
) -> Explanation:
    """Cache, then (only if allowed) the model, then the templates."""
    if not use_llm or not input.deltas:
        return _fallback_explanation(input, failures=[])

    cached = load_cached(input)
    if cached is not None:
        sentences, cached_version = cached
        # Re-checked on the way out: the checker may have tightened since the
        # sentences were written, and unchecked text never goes on the wire.
        if not check(sentences, input):
            return Explanation(
                text=templates.frame(input, sentences),
                sentences=sentences,
                checks_passed=True,
                fallback_used=False,
                check_failures=[],
                model_version=cached_version,
            )

    if not allow_live:
        return _fallback_explanation(input, failures=[])

    try:
        sentences = verbalise(input, client=client)
    except VerbaliserError as e:
        return _fallback_explanation(input, failures=[f"llm_error:{e}"])

    failures = check(sentences, input)
    if failures:
        try:
            sentences = verbalise(input, failure_codes=failures, client=client)
        except VerbaliserError as e:
            return _fallback_explanation(input, failures=failures + [f"llm_error:{e}"])
        failures = check(sentences, input)
        if failures:
            return _fallback_explanation(input, failures=failures)

    store_cached(input, sentences, model_version=explanation_model_version())
    return Explanation(
        text=templates.frame(input, sentences),
        sentences=sentences,
        checks_passed=True,
        fallback_used=False,
        check_failures=[],
        model_version=explanation_model_version(),
    )


def _fallback_explanation(input: ExplanationInput, *, failures: list[str]) -> Explanation:
    """Code-generated sentences. Self-checked so a template bug cannot ship silently."""
    sentences: list[Sentence] = templates.full_fallback(input)
    residual = check(sentences, input)
    return Explanation(
        text=templates.frame(input, sentences),
        sentences=sentences,
        checks_passed=not residual,
        fallback_used=bool(input.deltas) or bool(failures),
        check_failures=failures + [f"fallback_{c}" for c in residual],
        model_version=explanation_model_version(),
    )
