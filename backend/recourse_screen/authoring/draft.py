"""LLM #3: a job ad in, a draft job configuration out.

This is the only place the model is allowed near employer policy, and it is
fenced in hard. The structured-output grammar is built from the manifest, so the
model can only propose criteria that already exist as features — it cannot
invent one, and it cannot reach a protected attribute, because those paths are
not in the enum it emits from.

That fence is also the point. When an ad says "recent graduate" or "no career
breaks", the model has nowhere to put it except ``refused``, and the employer
sees, in the draft, that the system read the requirement and will not act on it.
A quiet omission would be worse than useless here: it would look like agreement.

The output is a proposal, never a saved job. It comes back as a
:class:`~.store.JobSpec` for a human to edit and save.
"""
from __future__ import annotations

import enum
import logging
from typing import Any

from pydantic import BaseModel, Field

from .. import config
from ..loaders import load_manifest
from ..schemas import BUDGET_TOTAL, FeatureSpec, Manifest
from . import budget
from .catalogue import knockout_for
from .store import JobSpec, ScoreLine

log = logging.getLogger(__name__)

MAX_TOKENS = 8000
EFFORT = "medium"
AD_OPEN = "<job_ad>"
AD_CLOSE = "</job_ad>"

__all__ = ["DraftError", "draft_from_ad"]


class DraftError(RuntimeError):
    """The model refused, or the API call failed in a way retrying will not fix."""


_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()
    return _client


# --------------------------------------------------------------------------- #
# The output grammar, built from the manifest
# --------------------------------------------------------------------------- #

def build_draft_model(usable: tuple[str, ...], protected: tuple[str, ...]) -> type[BaseModel]:
    """Build the draft output model with the manifest's feature paths as enums.

    Scored criteria and knockouts draw from ``usable`` only. ``protected`` is a
    separate enum used solely to report what the ad asked for and will not get,
    so an illegal configuration is not expressible in the grammar at all.
    """
    Usable = enum.Enum("UsablePath", {p: p for p in usable}, type=str)
    Protected = enum.Enum("ProtectedPath", {p: p for p in protected or ("none",)}, type=str)

    class Criterion(BaseModel):
        path: Usable = Field(  # type: ignore[valid-type]
            description="Which manifest feature this criterion scores."
        )
        points: int = Field(
            description=f"Share of the {BUDGET_TOTAL}-point budget at full marks. "
            "Bigger means the employer cares more. All criteria together should "
            f"total {BUDGET_TOTAL}."
        )
        full_marks_at: str = Field(
            description="The value that earns all of those points, in the feature's own "
            "unit: a number of months for experience, a count for projects, a ladder "
            "value for a degree level, 'true' for a yes/no feature. Everything above it "
            "scores the same, so set it where the employer stops caring about more -- "
            "for most roles that is around the level the ad asks for, not a career peak."
        )
        quote: str = Field(
            description="The phrase from the ad that justifies this criterion, verbatim. "
            "Empty string if the ad does not mention it and you are adding it as a "
            "sensible default for the role."
        )

    class HardRequirement(BaseModel):
        path: Usable = Field(  # type: ignore[valid-type]
            description="Which manifest feature must be satisfied before scoring starts."
        )
        minimum: str = Field(
            description="For a yes/no feature, 'true'. For a count of months, the number "
            "of months as digits. For a degree level, one of the ladder values. "
            "This is a floor, not a preference."
        )
        quote: str = Field(
            description="The phrase from the ad that makes this a hard requirement, verbatim. "
            "Only mark something a hard requirement if the ad is unambiguous about it "
            "('must have', 'required', 'minimum'); a wish goes in criteria instead."
        )

    class Refusal(BaseModel):
        path: Protected = Field(  # type: ignore[valid-type]
            description="The protected attribute the ad's requirement would need."
        )
        quote: str = Field(description="The phrase from the ad, verbatim.")

    class JobDraftOutput(BaseModel):
        title: str = Field(description="The role title, as the ad gives it.")
        criteria: list[Criterion] = Field(
            description="The weighted criteria, most important first. Six to ten is "
            "a good number; fewer than four makes a blunt screen."
        )
        hard_requirements: list[HardRequirement] = Field(
            description="Only genuinely binary, job-related requirements. Usually zero to three."
        )
        refused: list[Refusal] = Field(
            description="Requirements in the ad that would need an attribute this system "
            "refuses to use. Empty list if the ad asks for none."
        )
        unmapped: list[str] = Field(
            description="Requirements in the ad that are legitimate but have no matching "
            "feature in the vocabulary, quoted. These need a new feature before they can "
            "be screened on, so say so rather than approximating them with something else."
        )

    JobDraftOutput.__name__ = "JobDraftOutput"
    return JobDraftOutput


def _feature_line(path: str, spec: FeatureSpec) -> str:
    if spec.type == "bool":
        shape = "yes/no; full_marks_at is always 'true'"
    elif spec.type == "ordinal":
        shape = f"one of {' < '.join(spec.ladder or [])}"
    else:
        shape = (f"whole {spec.step.unit}, counted in steps of {spec.step.size}, "
                 f"ceiling {spec.domain_max * (spec.step.size or 1)}")
    return f"  {path} ({shape}) — {spec.candidate_phrase}"


def _system_prompt(manifest: Manifest) -> str:
    usable = [
        _feature_line(p, s)
        for p, s in manifest.features.items()
        if s.actionability != "protected_never_use"
    ]
    refused = [
        f"  {p} — {s.candidate_phrase} (refused: {s.reason})"
        for p, s in manifest.features.items()
        if s.actionability == "protected_never_use"
    ]
    return f"""\
You turn a job advertisement into a draft screening configuration for a hiring \
pre-screener. A human recruiter reviews and edits everything you produce before it \
scores anybody, so your job is a good, honest first draft — not a final answer.

The screen has exactly two parts.

HARD REQUIREMENTS are checked first and are never traded off against anything. Use \
them only where the ad is unambiguous ("must have", "required", "minimum N years"). \
They are expensive: a hard requirement removes a candidate outright, with no way to \
compensate. When in doubt, make it a weighted criterion instead.

WEIGHTED CRITERIA share a budget of exactly {BUDGET_TOTAL} points. How you split the \
budget is the employer's statement of what the role is actually about, so spend it the \
way the ad reads: a requirement the ad leads with and repeats deserves several times \
what a "nice to have" gets. Do not spread the budget evenly — an even split says \
nothing. Your points should add up to {BUDGET_TOTAL}; small arithmetic slips are \
corrected downstream.

You may only use the vocabulary below. It is fixed. If the ad asks for something that \
is not in it, quote the requirement in `unmapped` rather than forcing it onto a feature \
that means something else — an approximate match here becomes a wrong rejection later.

VOCABULARY (manifest {manifest.version}):
{chr(10).join(usable)}

NEVER AVAILABLE — these exist so the system can name what it refuses to use. They can \
never be scored or required, whatever the ad says. If the ad asks for one, report it in \
`refused` with the phrase that asked:
{chr(10).join(refused)}

Two things to watch for, because ads contain them often and they are exactly what this \
system exists to avoid:
- Proxies for age: "recent graduate", "digital native", a graduation-year window, \
"no more than N years since your degree".
- Proxies for caregiving or disability: "continuous employment", "no gaps in your CV", \
"no career breaks".
Report these in `refused`. Do not quietly approximate them with an experience \
requirement — that is the same discrimination wearing a different label.

Quote the ad verbatim in every `quote` field. If you are adding a criterion the ad does \
not mention because the role plainly needs it, leave the quote empty rather than \
inventing one.\
"""


def _user_message(ad_text: str) -> str:
    return f"{AD_OPEN}\n{ad_text.strip()}\n{AD_CLOSE}\n\nDraft the screening configuration."


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def draft_from_ad(
    ad_text: str,
    *,
    manifest_name: str = "data_science.json",
    job_id: str | None = None,
    threshold: int = 80,
    slots_n: int = 3,
) -> dict:
    """Draft a :class:`JobSpec` from a job ad. One LLM call, nothing saved.

    Returns the spec alongside what the model was refused and what it could not
    map, so the UI can show the employer the whole story rather than a config
    that silently dropped half their ad.
    """
    import anthropic

    if not ad_text.strip():
        raise DraftError("no job ad text to read")

    manifest = load_manifest(manifest_name)
    usable = tuple(
        p for p, s in manifest.features.items() if s.actionability != "protected_never_use"
    )
    protected = tuple(sorted(manifest.protected_paths()))
    output_model = build_draft_model(usable, protected)

    try:
        response = _get_client().messages.parse(
            model=config.MODEL_ID,
            max_tokens=MAX_TOKENS,
            system=[{
                "type": "text",
                "text": _system_prompt(manifest),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": _user_message(ad_text)}],
            output_format=output_model,
            output_config={"effort": EFFORT},
        )
    except anthropic.RateLimitError as exc:
        raise DraftError(f"rate limited after SDK retries: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise DraftError(f"API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise DraftError(f"could not reach the API: {exc}") from exc

    if response.stop_reason == "refusal":
        raise DraftError("the model declined to draft from this ad; write the config by hand")
    if response.stop_reason == "max_tokens":
        raise DraftError(f"output hit max_tokens ({MAX_TOKENS}); the draft would be truncated")
    parsed = response.parsed_output
    if parsed is None:
        raise DraftError("structured output came back empty")

    return _to_spec(
        parsed, manifest, manifest_name,
        job_id=job_id, threshold=threshold, slots_n=slots_n,
    )


def _cap_from(spec: FeatureSpec, full_marks_at: str) -> int:
    """How many solver steps count as full marks, from the value the model named.

    Falls back to the feature's whole domain only when the value is unreadable.
    That fallback matters: ``domain_max`` for experience is twenty years, and
    quietly using it would make one criterion swallow the entire budget.
    """
    from ..score.features import raw_to_steps

    value = full_marks_at.strip()
    if spec.type == "bool":
        return 1
    if spec.type == "ordinal":
        ladder = spec.ladder or []
        return max(1, ladder.index(value)) if value in ladder else max(1, len(ladder) // 2)
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return max(1, spec.domain_max)
    return max(1, min(spec.domain_max, raw_to_steps(spec, int(digits))))


def _refusal_reason(manifest: Manifest, path: str) -> str:
    spec = manifest.features.get(path)
    return (spec.reason if spec and spec.reason else "protected attribute")


def _path_of(field: Any) -> str:
    """Enum members come back as members here and as plain strings from a replay."""
    return str(getattr(field, "value", field))


def _slug(title: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in title.strip()]
    return "".join(keep).strip("_").replace("__", "_") or "untitled_job"


def _to_spec(
    parsed: Any,
    manifest: Manifest,
    manifest_name: str,
    *,
    job_id: str | None,
    threshold: int,
    slots_n: int,
) -> dict:
    """Model output -> a JobSpec the UI can edit, plus what we could not honour."""
    caps: dict[str, int] = {}
    asked: dict[str, int] = {}
    quotes: dict[str, str] = {}
    for c in parsed.criteria:
        path = _path_of(c.path)
        spec = manifest.features.get(path)
        if spec is None or spec.actionability == "protected_never_use":
            continue  # the grammar should prevent this; belt and braces
        caps[path] = _cap_from(spec, c.full_marks_at)
        asked[path] = max(0, int(c.points))
        if c.quote.strip():
            quotes[path] = c.quote.strip()

    if not asked:
        raise DraftError("the draft came back with no usable criteria")

    allocation = budget.normalise(asked, caps)

    knockouts: list[str] = []
    for hr in parsed.hard_requirements:
        path = _path_of(hr.path)
        spec = manifest.features.get(path)
        if spec is None or spec.actionability == "protected_never_use":
            continue
        value = hr.minimum.strip()
        if spec.type == "bool":
            rule = knockout_for(path, spec, value.lower() not in ("false", "no", "0", ""))
        elif spec.type == "ordinal":
            if value not in (spec.ladder or []):
                continue
            rule = knockout_for(path, spec, value)
        else:
            digits = "".join(ch for ch in value if ch.isdigit())
            if not digits:
                continue
            rule = knockout_for(path, spec, int(digits))
        if rule not in knockouts:
            knockouts.append(rule)

    title = parsed.title.strip() or "Untitled role"
    spec = JobSpec(
        job_id=job_id or _slug(title),
        title=title,
        family=manifest.job_family,
        manifest=manifest_name,
        version="draft-v1",
        knockouts=knockouts,
        score={p: ScoreLine(points=n, cap=caps[p]) for p, n in allocation.items()},
        threshold=threshold,
        slots_n=slots_n,
    )
    return {
        "spec": spec.model_dump(),
        "quotes": quotes,
        "refused": [
            {
                "path": _path_of(r.path),
                "quote": r.quote.strip(),
                "reason": _refusal_reason(manifest, _path_of(r.path)),
            }
            for r in parsed.refused
        ],
        "unmapped": [u.strip() for u in parsed.unmapped if u.strip()],
        "adjusted": {
            p: {"asked": asked[p], "applied": allocation.get(p, 0)}
            for p in asked
            if asked[p] != allocation.get(p, 0)
        },
    }
