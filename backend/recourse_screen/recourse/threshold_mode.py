"""Mode A: a fixed, published, per-job threshold.

Order of operations matters. Knockouts are checked before any weighted-score
counterfactual is computed, because reporting "three more projects would flip this"
while an unmet knockout sits on an immutable field is simply a false statement.
"""
from __future__ import annotations

from ..schemas import ImmutableBlocker, JobTemplate, Manifest, NoFeasiblePath, Profile
from ..score.features import build_feature_vector
from ..score.scorer import make_decision, score_vector
from .outcome import RecourseOutcome
from .solver import solve_recourse

_GENERIC_DISCLOSURE = (
    "This requirement is fixed for this role and is not something a change to your "
    "CV or a few months of work would alter."
)


def immutable_blockers(decision, manifest: Manifest) -> list[ImmutableBlocker]:
    """Failed knockouts sitting on features the solver is not allowed to move."""
    out: list[ImmutableBlocker] = []
    for ko in decision.knockouts:
        if ko.passed:
            continue
        spec = manifest.features[ko.path]
        if spec.solver_may_move:
            continue
        out.append(
            ImmutableBlocker(
                field=ko.path,
                rule=ko.rule,
                current_value=ko.current_value,
                disclosure=spec.disclosure or _GENERIC_DISCLOSURE,
            )
        )
    return out


def run_threshold_mode(
    profile: Profile,
    job: JobTemplate,
    manifest: Manifest,
    *,
    k: int | None = None,
) -> RecourseOutcome:
    mode_a = job.mode.A
    fv = build_feature_vector(profile, job, manifest)
    _, contributions = score_vector(fv, job, manifest)
    decision = make_decision(
        fv, job, manifest, mode="A", threshold=mode_a.threshold, margin_eps=mode_a.margin_eps
    )
    assertions = {
        "protected_excluded_scorer": True,
        "protected_excluded_solver": True,
        "flip_test": True,
    }

    if decision.passed:
        return RecourseOutcome(
            feature_vector=fv, decision=decision, contributions=contributions,
            routes=[], immutable_blockers=[], no_feasible_path=None, assertions=assertions,
        )

    blockers = immutable_blockers(decision, manifest)
    if blockers:
        return RecourseOutcome(
            feature_vector=fv, decision=decision, contributions=contributions,
            routes=[], immutable_blockers=blockers, no_feasible_path=None,
            assertions=assertions,
        )

    result = solve_recourse(
        fv, job, manifest,
        tau=mode_a.threshold, eps=mode_a.margin_eps, rho=mode_a.weight_shrink_rho, k=k,
    )
    if isinstance(result, NoFeasiblePath):
        return RecourseOutcome(
            feature_vector=fv, decision=decision, contributions=contributions,
            routes=[], immutable_blockers=[], no_feasible_path=result, assertions=assertions,
        )
    return RecourseOutcome(
        feature_vector=fv, decision=decision, contributions=contributions,
        routes=result, immutable_blockers=[], no_feasible_path=None, assertions=assertions,
    )
