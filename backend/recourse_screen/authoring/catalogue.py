"""What HR is allowed to build a job out of.

The authoring UI never invents a criterion: it picks from the manifest. This
module is the projection of a manifest into the shape that UI needs — every
usable feature, what it is called in plain English, and for the knockout
checklist, the rule string that a tick actually produces.

Protected features are reported separately rather than omitted. "We hold a
graduation year and refuse to score it" is a stronger claim than silence, and it
is the thing an auditor asks about.
"""
from __future__ import annotations

from typing import Any

from ..schemas import FeatureSpec, JobTemplate, Manifest, effective_dependencies

__all__ = ["catalogue_for", "default_knockout", "knockout_for"]


def default_knockout(path: str, spec: FeatureSpec) -> str | None:
    """The rule a plain tick in the checklist means, before HR edits the number.

    ``None`` for a feature that cannot carry a sensible hard requirement.
    """
    if spec.type == "bool":
        return f"{path} == true"
    if spec.type == "ordinal":
        ladder = spec.ladder or []
        if not ladder:
            return None
        # Default to the middle of the ladder rather than the top: a knockout is a
        # floor, and proposing "PhD required" as the starting point would be absurd.
        return f"{path} >= {ladder[len(ladder) // 2]}"
    step = spec.step.size or 1
    return f"{path} >= {step * 2}"


def knockout_for(path: str, spec: FeatureSpec, value: Any) -> str:
    """The rule string for a checklist tick carrying an explicit value."""
    if spec.type == "bool":
        return f"{path} == {'true' if value else 'false'}"
    return f"{path} >= {value}"


def _feature_entry(path: str, spec: FeatureSpec) -> dict:
    return {
        "path": path,
        "phrase": spec.candidate_phrase,
        "type": spec.type,
        "unit": spec.step.unit,
        "step_size": spec.step.size,
        "domain_max": spec.domain_max,
        "ladder": spec.ladder,
        "actionability": spec.actionability,
        "cost_per_step": spec.cost_per_step,
        "max_delta": spec.max_delta,
        "typical_time_months": spec.typical_time_months,
        "is_causal": spec.is_causal,
        "disclosure": spec.disclosure,
        # A cap of 1 step is the finest granularity, so its points can be any
        # integer; coarser features can only be worth multiples of their cap.
        "default_cap": max(1, spec.domain_max),
        "knockout_template": default_knockout(path, spec),
        "can_knockout": spec.actionability != "protected_never_use",
    }


def catalogue_for(manifest: Manifest, job: JobTemplate | None = None) -> dict:
    """Everything the authoring UI needs to build or edit a job on this manifest."""
    usable: list[dict] = []
    refused: list[dict] = []
    for path, spec in manifest.features.items():
        if spec.actionability == "protected_never_use":
            refused.append({
                "path": path,
                "phrase": spec.candidate_phrase,
                "reason": spec.reason or "protected attribute",
            })
            continue
        usable.append(_feature_entry(path, spec))

    deps = effective_dependencies(job, manifest) if job is not None else manifest.parsed_dependencies
    return {
        "job_family": manifest.job_family,
        "manifest_version": manifest.version,
        "horizon_months": manifest.horizon_months,
        "features": usable,
        "protected_never_use": refused,
        # Causal constraints are shown, never edited here: they are facts about
        # how skills are acquired, not an employer's value judgement.
        "dependencies": [{"rule": d.rule, "gloss": d.gloss(manifest)} for d in deps],
    }
