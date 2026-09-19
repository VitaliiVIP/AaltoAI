"""Project a Profile through a Manifest + JobTemplate into an integer FeatureVector.

Two rules are enforced here rather than trusted elsewhere:

* boundary assertion #2 -- a feature whose actionability is ``protected_never_use``
  may never reach the scorer, so asking for one raises :class:`ProtectedFeatureError`;
* every value the rest of the pipeline sees is an integer number of *solver steps*,
  so CP-SAT stays exact and no rounding can silently invalidate a route.

``raw_value`` keeps the value as it appeared in the profile (``None`` when the field
is absent), which is what knockouts are evaluated against.  ``steps`` may differ from
``raw_value`` when a scored field is absent and the job template grants an
``absent_prior``: the prior credits score, it never satisfies a knockout.
"""
from __future__ import annotations

from typing import Any

from ..schemas import (
    FeatureSpec,
    FeatureValue,
    FeatureVector,
    JobTemplate,
    Manifest,
    Profile,
)


class ProtectedFeatureError(Exception):
    """A protected attribute was requested by a job template."""


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def raw_to_steps(spec: FeatureSpec, raw: Any) -> int:
    """Convert a raw profile value into integer solver steps, clamped to the domain."""
    if raw is None:
        return 0
    if spec.type == "bool":
        return 1 if bool(raw) else 0
    if spec.type == "ordinal":
        ladder = spec.ladder or []
        idx = ladder.index(raw) if raw in ladder else 0
        return _clamp(idx, 0, spec.domain_max)
    size = spec.step.size or 1
    return _clamp(int(raw) // size, 0, spec.domain_max)


def steps_to_raw(spec: FeatureSpec, steps: int) -> Any:
    """Inverse of :func:`raw_to_steps` (lossy for ints: returns the step boundary)."""
    if spec.type == "bool":
        return steps >= 1
    if spec.type == "ordinal":
        ladder = spec.ladder or []
        if not ladder:
            return steps
        return ladder[_clamp(steps, 0, len(ladder) - 1)]
    return steps * (spec.step.size or 1)


def job_feature_paths(job: JobTemplate) -> list[str]:
    """Every manifest path the job template refers to, in a stable order:
    scored features first, then knockout-only, then dependency-only."""
    paths: list[str] = list(job.score.keys())
    for ko in job.parsed_knockouts:
        if ko.path not in paths:
            paths.append(ko.path)
    for dep in job.parsed_dependencies:
        for p in (dep.a, dep.b):
            if p and p not in paths:
                paths.append(p)
    return paths


def build_feature_vector(profile: Profile, job: JobTemplate, manifest: Manifest) -> FeatureVector:
    """Resolve every path the job needs into a :class:`FeatureValue`.

    Raises:
        ProtectedFeatureError: the job references a ``protected_never_use`` feature.
        KeyError: the job references a path the manifest does not declare.
    """
    fv: FeatureVector = {}
    for path in job_feature_paths(job):
        spec = manifest.features.get(path)
        if spec is None:
            raise KeyError(f"job {job.job_id!r} references unknown manifest feature: {path}")
        if spec.actionability == "protected_never_use":
            raise ProtectedFeatureError(
                f"job {job.job_id!r} references protected feature {path!r} "
                f"({spec.reason or 'protected_never_use'}); protected attributes never enter the scorer"
            )
        env = profile.resolve(path)
        term = job.score.get(path)
        prior_applied = False
        if env.is_known:
            steps = raw_to_steps(spec, env.value)
            raw_value = env.value
        else:
            raw_value = env.value  # None, or a falsy placeholder from Profile.resolve
            steps = 0
            # A denied field is a stated "no" and never earns a prior.
            if env.derivation != "denied" and term is not None and term.absent_prior > 0:
                steps = _clamp(term.absent_prior, 0, spec.domain_max)
                prior_applied = True
        fv[path] = FeatureValue(
            path=path,
            steps=steps,
            raw_value=raw_value,
            derivation=env.derivation,
            confidence=env.confidence,
            prior_applied=prior_applied,
        )
    return fv
