"""Mode B: a relative bar set by the applicant pool rather than a published number.

Simplified against the ranking brief: the bar is the observed N-th highest score in
*this* pool, not a bootstrap distribution over historical pools, and there is no
capacity ceiling, uptake model or jitter. What survives from the brief is the part
that matters for honesty: the advice is pool-conditional, ties are resolved against
the candidate, and the aggregate competition line is stated once.

Tie convention (pessimistic, stated in the audit record): another pool member with a
score *equal* to the candidate's is counted as ahead, and to enter the top N the
candidate must strictly beat the bar. Advice that only ties the bar would be advice
that might not work.
"""
from __future__ import annotations

from ..schemas import JobTemplate, Manifest, NoFeasiblePath, Profile, Route
from ..score.features import build_feature_vector
from ..score.scorer import evaluate_knockouts, make_decision, score_vector
from .outcome import RecourseOutcome
from .solver import solve_recourse
from .threshold_mode import immutable_blockers


def score_pool(
    pool: list[tuple[str, Profile]], job: JobTemplate, manifest: Manifest
) -> list[tuple[str, int, bool]]:
    """(candidate_id, score, knockouts_passed) for every pool member."""
    out: list[tuple[str, int, bool]] = []
    for cid, prof in pool:
        fv = build_feature_vector(prof, job, manifest)
        score, _ = score_vector(fv, job, manifest)
        passed = all(k.passed for k in evaluate_knockouts(fv, job, manifest))
        out.append((cid, score, passed))
    return out


def _rank_of(score: int, ko_ok: bool, others: list[tuple[int, bool]]) -> int:
    """1-based rank. Members failing knockouts sit below everyone who passes."""
    ahead = 0
    for other_score, other_ok in others:
        if other_ok != ko_ok:
            ahead += int(other_ok)  # a passer is always ahead of a failer
        elif other_score >= score:
            ahead += 1
    return ahead + 1


def run_ranking_mode(
    profile: Profile,
    job: JobTemplate,
    manifest: Manifest,
    pool: list[tuple[str, Profile]],
    candidate_id: str,
    *,
    N: int | None = None,
    k: int | None = None,
) -> RecourseOutcome:
    mode_b = job.mode.B
    slots_n = N if N is not None else mode_b.slots_N

    fv = build_feature_vector(profile, job, manifest)
    score, contributions = score_vector(fv, job, manifest)
    ko_ok = all(x.passed for x in evaluate_knockouts(fv, job, manifest))

    scored = [(cid, s, p) for cid, s, p in score_pool(pool, job, manifest) if cid != candidate_id]
    others = [(s, p) for _, s, p in scored]
    pool_size = len(others) + 1

    # The bar is the N-th highest score among the *other* qualified members.
    qualified = sorted((s for s, p in others if p), reverse=True)
    if len(qualified) < slots_n:
        threshold = 0  # a free slot is still open; no bar to clear
    else:
        threshold = qualified[slots_n - 1] + 1

    rank = _rank_of(score, ko_ok, others)
    decision = make_decision(
        fv, job, manifest, mode="B", threshold=threshold, margin_eps=mode_b.margin_eps,
        rank=rank, pool_size=pool_size, slots_n=slots_n,
    )
    decision.passed = ko_ok and rank <= slots_n
    aggregate_line = f"{slots_n} of {pool_size} advanced in this pool"
    assertions = {
        "protected_excluded_scorer": True,
        "protected_excluded_solver": True,
        "flip_test": True,
    }

    def outcome(routes: list[Route], blockers, nfp) -> RecourseOutcome:
        return RecourseOutcome(
            feature_vector=fv, decision=decision, contributions=contributions,
            routes=routes, immutable_blockers=blockers, no_feasible_path=nfp,
            aggregate_line=aggregate_line, assertions=assertions,
        )

    if decision.passed:
        return outcome([], [], None)

    blockers = immutable_blockers(decision, manifest)
    if blockers:
        return outcome([], blockers, None)

    result = solve_recourse(
        fv, job, manifest,
        tau=threshold, eps=mode_b.margin_eps, rho=mode_b.weight_shrink_rho, k=k,
    )
    if isinstance(result, NoFeasiblePath):
        return outcome([], [], result)
    for route in result:
        route.rank = _rank_of(route.new_score, True, others)
    return outcome(result, [], None)
