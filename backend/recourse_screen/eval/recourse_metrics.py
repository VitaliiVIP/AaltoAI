"""Solver-side evaluation.

Rows 1, 5, 6, 8 and 9 of the metrics table in
research/notes/ranking_mode_gaming_and_evaluation_brief.md:

  1  recourse validity  - every returned route must actually clear the bar
  5  proximity / cost   - mean and median cost of the cheapest route
  6  sparsity           - L0, the number of features a route changes
  8  diversity          - distinct changed-feature sets among the k routes
  9  actionability rate - rejected candidates with at least one feasible route

plus the two honesty counters the demo turns on: how often a rejection is
explained by an immutable blocker, and how often no feasible path exists at all.

`summarise_outcomes` is pure aggregation over objects with the `RecourseOutcome`
shape, so it is testable without running CP-SAT.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Literal, Sequence

from ..schemas import Profile


def _routes(outcome: Any) -> list[Any]:
    return list(getattr(outcome, "routes", None) or [])


def _support(route: Any) -> frozenset[str]:
    return frozenset(d.field for d in getattr(route, "deltas", []) or [])


def _route_is_valid(route: Any, threshold: int | None) -> bool:
    """Trust the solver's own flip test, and independently re-check the reported
    new score against the bar. Both must hold."""
    if not bool(getattr(route, "flip_test_passed", False)):
        return False
    if threshold is None:
        return True
    new_score = getattr(route, "new_score", None)
    return new_score is not None and int(new_score) >= int(threshold)


def summarise_outcomes(outcomes: Sequence[Any], *, mode: str,
                       ids: Sequence[str] | None = None) -> dict[str, Any]:
    """Aggregate a list of RecourseOutcome-shaped objects. `ids` labels the rows of
    the per-candidate table; it must line up with `outcomes` when given."""
    n = len(outcomes)
    labels = list(ids) if ids is not None else [getattr(o, "candidate_id", None) for o in outcomes]
    if len(labels) != n:
        raise ValueError("ids must line up with outcomes")
    pairs = list(zip(labels, outcomes))
    passed = [o for _, o in pairs if bool(getattr(o.decision, "passed", False))]
    rejected = [(c, o) for c, o in pairs if not bool(getattr(o.decision, "passed", False))]

    n_routes = 0
    n_valid = 0
    l0s: list[int] = []
    costs: list[int] = []
    cheapest: list[int] = []
    diversity: list[int] = []
    with_route = 0
    blocked = 0
    no_path = 0
    per_candidate: list[dict[str, Any]] = []

    for cid, o in rejected:
        thr = getattr(o.decision, "threshold", None)
        rs = _routes(o)
        valid_flags = [_route_is_valid(r, thr) for r in rs]
        n_routes += len(rs)
        n_valid += sum(valid_flags)
        if rs:
            with_route += 1
            route_l0 = [len(getattr(r, "deltas", []) or []) for r in rs]
            route_cost = [int(getattr(r, "cost", 0)) for r in rs]
            l0s.extend(route_l0)
            costs.extend(route_cost)
            cheapest.append(min(route_cost))
            diversity.append(len({_support(r) for r in rs}))
        if getattr(o, "immutable_blockers", None):
            blocked += 1
        if getattr(o, "no_feasible_path", None) is not None:
            no_path += 1
        per_candidate.append({
            "candidate_id": cid,
            "score": getattr(o.decision, "score", None),
            "threshold": thr,
            "rank": getattr(o.decision, "rank", None),
            "n_routes": len(rs),
            "all_routes_valid": bool(rs) and all(valid_flags),
            "l0": [len(getattr(r, "deltas", []) or []) for r in rs],
            "cost": [int(getattr(r, "cost", 0)) for r in rs],
            "immutable_blockers": len(getattr(o, "immutable_blockers", None) or []),
            "no_feasible_path": getattr(o, "no_feasible_path", None) is not None,
        })

    def ratio(a: float, b: float) -> float:
        return float(a) / float(b) if b else 0.0

    return {
        "mode": mode,
        "n_candidates": n,
        "n_passed": len(passed),
        "n_rejected": len(rejected),
        "pass_rate": ratio(len(passed), n),
        "n_routes": n_routes,
        "validity": ratio(n_valid, n_routes),
        "validity_per_candidate": ratio(
            sum(1 for c in per_candidate if c["all_routes_valid"]), max(1, with_route)
        ) if with_route else 0.0,
        "actionability_rate": ratio(with_route, len(rejected)),
        "l0_mean": ratio(sum(l0s), len(l0s)) if l0s else None,
        "l0_max": max(l0s) if l0s else None,
        "cost_mean": ratio(sum(costs), len(costs)) if costs else None,
        "cost_median": float(median(costs)) if costs else None,
        "cheapest_route_cost_median": float(median(cheapest)) if cheapest else None,
        "diversity_mean_distinct_supports": ratio(sum(diversity), len(diversity)) if diversity else None,
        "immutable_blocker_rate": ratio(blocked, len(rejected)),
        "no_feasible_path_rate": ratio(no_path, len(rejected)),
        "per_candidate": per_candidate,
    }


def recourse_metrics(
    profiles: list[tuple[str, Profile]],
    job,
    manifest,
    *,
    mode: Literal["A", "B"],
    N: int | None = None,
    k: int | None = None,
) -> dict[str, Any]:
    """Run mode A (threshold) or mode B (ranking, whole list as the pool) over the
    corpus and summarise. Solver modules are imported lazily so this file stays
    importable while they are still being built."""
    outcomes: list[Any] = []
    ids: list[str] = []
    errors: list[dict[str, str]] = []
    if mode == "A":
        from ..recourse.threshold_mode import run_threshold_mode
    else:
        from ..recourse.ranking_mode import run_ranking_mode

    for cid, profile in profiles:
        try:
            if mode == "A":
                outcome = run_threshold_mode(profile, job, manifest, k=k)
            else:
                outcome = run_ranking_mode(profile, job, manifest, profiles, cid, N=N, k=k)
        except Exception as exc:
            errors.append({"candidate_id": cid, "error": repr(exc)})
            continue
        outcomes.append(outcome)
        ids.append(cid)

    summary = summarise_outcomes(outcomes, mode=mode, ids=ids)
    summary["errors"] = errors
    summary["n_errors"] = len(errors)
    return summary
