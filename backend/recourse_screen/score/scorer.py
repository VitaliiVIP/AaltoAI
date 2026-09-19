"""The interpretable scorer: an additive integer sum plus a knockout conjunction.

The knockout conjunction is kept strictly outside the weighted sum. Folding a hard
requirement in as a large weight is what makes recourse engines emit nonsense
trade-offs ("compensate for missing work authorisation with four side projects").
"""
from __future__ import annotations

from typing import Literal

from ..schemas import (
    Decision,
    FeatureContribution,
    FeatureVector,
    JobTemplate,
    KnockoutResult,
    Manifest,
    ScoreTerm,
)


def cap_for(spec, term: ScoreTerm) -> int:
    """A score term's cap in steps; ``None`` means the feature's whole domain."""
    return spec.domain_max if term.cap is None else term.cap


def score_vector(
    fv: FeatureVector, job: JobTemplate, manifest: Manifest
) -> tuple[int, list[FeatureContribution]]:
    """Return the additive score and the per-feature contributions behind it."""
    total = 0
    contributions: list[FeatureContribution] = []
    for path, term in job.score.items():
        spec = manifest.features[path]
        fval = fv[path]
        cap = cap_for(spec, term)
        effective = min(fval.steps, cap)
        contribution = term.weight * effective
        total += contribution
        contributions.append(
            FeatureContribution(
                path=path,
                phrase=spec.candidate_phrase,
                steps=fval.steps,
                cap=cap,
                weight=term.weight,
                contribution=contribution,
                max_contribution=term.weight * cap,
                raw_value=fval.raw_value,
                derivation=fval.derivation,
                prior_applied=fval.prior_applied,
            )
        )
    return total, contributions


def evaluate_knockouts(
    fv: FeatureVector, job: JobTemplate, manifest: Manifest
) -> list[KnockoutResult]:
    """Evaluate each knockout against the *raw* profile value, not the step value."""
    results: list[KnockoutResult] = []
    for ko in job.parsed_knockouts:
        spec = manifest.features[ko.path]
        fval = fv[ko.path]
        results.append(
            KnockoutResult(
                rule=ko.rule,
                path=ko.path,
                passed=ko.holds(fval.raw_value, spec),
                current_value=fval.raw_value,
                actionability=spec.actionability,
            )
        )
    return results


def max_score(job: JobTemplate, manifest: Manifest) -> int:
    """The highest score this job template can award."""
    return sum(
        term.weight * cap_for(manifest.features[path], term)
        for path, term in job.score.items()
    )


def make_decision(
    fv: FeatureVector,
    job: JobTemplate,
    manifest: Manifest,
    mode: Literal["A", "B"],
    threshold: int,
    margin_eps: int = 0,
    rank: int | None = None,
    pool_size: int | None = None,
    slots_n: int | None = None,
) -> Decision:
    """Assemble the decision. The robustness margin is a *solver* target only: it
    never makes a decision stricter than the employer's published threshold."""
    score, _ = score_vector(fv, job, manifest)
    knockouts = evaluate_knockouts(fv, job, manifest)
    knockouts_passed = all(k.passed for k in knockouts)
    return Decision(
        mode=mode,
        passed=knockouts_passed and score >= threshold,
        score=score,
        knockouts_passed=knockouts_passed,
        knockouts=knockouts,
        threshold=threshold,
        margin_eps=margin_eps,
        rank=rank,
        pool_size=pool_size,
        slots_n=slots_n,
        max_score=max_score(job, manifest),
    )
