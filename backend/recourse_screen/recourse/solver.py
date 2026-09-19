"""Minimum-cost integer recourse on OR-Tools CP-SAT.

Port of research/notes/recourse_toy_cpsat.py onto the real schema. Everything is in
integer *steps*, so there is no rounding step that could silently invalidate a route.

Model, per job template:

    minimise   sum_j cost_j * a_j  +  lambda * sum_j u_j
    subject to x'_j = x_j + a_j,  0 <= a_j <= min(max_delta_j, upper_j - x_j)
               a_j <= max_delta_j * u_j,   a_j >= u_j          (used indicator)
               sum_j (w_j - rho) * x'_j >= tau + eps           (robust flip)
               knockout bounds on x'
               dependencies (level_le / delta_le, both linear)

Only features whose spec says ``solver_may_move`` get variables; protected features
are asserted absent (boundary assertion #3). ``upper_j`` is the score cap for scored
features, so a feature already at its cap is frozen and can never be recommended --
the bug that told a Docker user to learn Docker.

Diversity uses support-disjoint cuts rather than no-good cuts: each new route must
touch a feature no earlier route touched, which yields different *stories* instead of
near-duplicates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ortools.sat.python import cp_model

from ..schemas import (
    Delta,
    FeatureSpec,
    FeatureValue,
    FeatureVector,
    JobTemplate,
    Manifest,
    NoFeasiblePath,
    Route,
)
from ..score.features import steps_to_raw
from ..score.scorer import cap_for, evaluate_knockouts, score_vector

_STATUS_OK = (cp_model.OPTIMAL, cp_model.FEASIBLE)


@dataclass
class _Feature:
    """One column of the program: either a variable or a frozen constant."""

    path: str
    spec: FeatureSpec
    x: int  # current steps
    cap: int | None  # score cap in steps; None when the feature is not scored
    weight: int  # 0 when not scored
    upper: int  # upper bound on x'
    max_a: int  # 0 => frozen
    a: Any = None
    xp: Any = None
    u: Any = None

    @property
    def movable(self) -> bool:
        return self.a is not None


def _ko_steps(spec: FeatureSpec, value: Any, *, lower: bool) -> int:
    """Convert a knockout's raw threshold into steps.

    Step granularity loses precision for int features whose threshold is not a
    multiple of the step size, so lower bounds round up and upper bounds round down:
    the solver is never allowed to claim a knockout is met when it might not be.
    """
    if spec.type == "bool":
        return 1 if bool(value) else 0
    if spec.type == "ordinal":
        ladder = spec.ladder or []
        return ladder.index(value) if value in ladder else 0
    size = spec.step.size or 1
    v = int(value)
    return -(-v // size) if lower else v // size


def _knockout_bounds(job: JobTemplate, manifest: Manifest) -> dict[str, tuple[int, int]]:
    """path -> (min steps, max steps) implied by the job's knockouts."""
    bounds: dict[str, tuple[int, int]] = {}
    for ko in job.parsed_knockouts:
        spec = manifest.features[ko.path]
        lo, hi = bounds.get(ko.path, (0, spec.domain_max))
        if ko.op == ">=":
            lo = max(lo, _ko_steps(spec, ko.value, lower=True))
        elif ko.op == ">":
            lo = max(lo, _ko_steps(spec, ko.value, lower=True) + 1)
        elif ko.op == "<=":
            hi = min(hi, _ko_steps(spec, ko.value, lower=False))
        elif ko.op == "<":
            hi = min(hi, _ko_steps(spec, ko.value, lower=False) - 1)
        else:  # "=="
            v = _ko_steps(spec, ko.value, lower=True)
            lo, hi = max(lo, v), min(hi, v)
        bounds[ko.path] = (lo, hi)
    return bounds


def _build_features(
    fv: FeatureVector, job: JobTemplate, manifest: Manifest
) -> dict[str, _Feature]:
    ko_bounds = _knockout_bounds(job, manifest)
    feats: dict[str, _Feature] = {}
    for path, fval in fv.items():
        spec = manifest.features[path]
        # Boundary assertion #3: a protected attribute must never reach the action set.
        assert spec.actionability != "protected_never_use", (
            f"protected feature {path!r} reached the solver"
        )
        term = job.score.get(path)
        cap = cap_for(spec, term) if term is not None else None
        weight = term.weight if term is not None else 0
        upper = cap if cap is not None else spec.domain_max
        ko_lo = ko_bounds.get(path, (0, spec.domain_max))[0]
        if cap is not None and ko_lo > cap:
            raise ValueError(
                f"{path}: knockout needs {ko_lo} steps but the score cap is {cap}; "
                "raise the cap or make the feature knockout-only"
            )
        max_a = min(spec.max_delta, upper - fval.steps) if spec.solver_may_move else 0
        feats[path] = _Feature(
            path=path, spec=spec, x=fval.steps, cap=cap, weight=weight,
            upper=upper, max_a=max(0, max_a),
        )
    return feats


def _add_vars(m: cp_model.CpModel, feats: dict[str, _Feature]) -> None:
    for f in feats.values():
        if f.max_a <= 0:
            continue
        f.a = m.NewIntVar(0, f.max_a, f"a[{f.path}]")
        f.xp = m.NewIntVar(0, f.upper, f"x'[{f.path}]")
        f.u = m.NewBoolVar(f"u[{f.path}]")
        m.Add(f.xp == f.x + f.a)
        m.Add(f.a <= f.max_a * f.u)
        m.Add(f.a >= f.u)


def _xp_expr(f: _Feature) -> Any:
    return f.xp if f.movable else f.x


def _a_expr(f: _Feature) -> Any:
    return f.a if f.movable else 0


def _score_expr(feats: dict[str, _Feature], job: JobTemplate, rho: int) -> Any:
    """sum_j (w_j - rho) * min(x'_j, cap_j). x'_j <= cap_j holds by construction for
    scored features, so the min is already resolved."""
    terms = []
    for path in job.score:
        f = feats[path]
        cap = f.cap if f.cap is not None else f.upper
        w = f.weight - rho
        terms.append(w * _xp_expr(f) if f.movable else w * min(f.x, cap))
    return sum(terms)


def _add_structural_constraints(
    m: cp_model.CpModel, feats: dict[str, _Feature], job: JobTemplate, manifest: Manifest
) -> bool:
    """Knockouts and dependencies. Returns False if the current constants already
    violate a constraint no variable can repair."""
    for path, (lo, hi) in _knockout_bounds(job, manifest).items():
        f = feats[path]
        if f.movable:
            m.Add(f.xp >= lo)
            m.Add(f.xp <= hi)
        elif not (lo <= f.x <= hi):
            return False
    for dep in job.parsed_dependencies:
        if dep.kind == "level_le":
            fa, fb = feats.get(dep.a), feats.get(dep.b)
            if fa is None or fb is None:
                continue
            if not fa.movable and not fb.movable:
                if fa.x > fb.x:
                    return False
                continue
            m.Add(_xp_expr(fa) <= _xp_expr(fb))
        else:  # delta_le: a[dep.a] <= c + k * a[dep.b]
            fa = feats.get(dep.a)
            if fa is None or not fa.movable:
                continue
            fb = feats.get(dep.b) if dep.b else None
            rhs = dep.c + (dep.k * _a_expr(fb) if fb is not None else 0)
            m.Add(fa.a <= rhs)
    return True


def _apply(fv: FeatureVector, actions: dict[str, int], manifest: Manifest) -> FeatureVector:
    """The counterfactual feature vector, with raw values re-derived for moved fields."""
    out: FeatureVector = {}
    for path, fval in fv.items():
        delta = actions.get(path, 0)
        if delta <= 0:
            out[path] = fval
            continue
        spec = manifest.features[path]
        steps = fval.steps + delta
        out[path] = FeatureValue(
            path=path,
            steps=steps,
            raw_value=steps_to_raw(spec, steps),
            derivation=fval.derivation,
            confidence=fval.confidence,
            prior_applied=fval.prior_applied,
        )
    return out


def _make_route(
    route_id: str,
    fv: FeatureVector,
    actions: dict[str, int],
    feats: dict[str, _Feature],
    job: JobTemplate,
    manifest: Manifest,
    *,
    tau: int,
    eps: int,
    flip_required: bool,
) -> Route:
    new_fv = _apply(fv, actions, manifest)
    new_score, _ = score_vector(new_fv, job, manifest)
    kos = evaluate_knockouts(new_fv, job, manifest)
    kos_ok = all(k.passed for k in kos)
    flip_ok = new_score >= tau + eps and kos_ok
    if flip_required and not flip_ok:
        # Soundness guarantee: a route we would show must actually flip the decision.
        raise RuntimeError(
            f"flip test failed for {route_id}: score {new_score} < {tau + eps} "
            f"or knockouts {[k.rule for k in kos if not k.passed]}"
        )

    deltas: list[Delta] = []
    cost = 0
    time_months = 0
    for i, (path, steps) in enumerate(sorted(actions.items()), start=1):
        if steps <= 0:
            continue
        f = feats[path]
        spec = f.spec
        step_cost = (spec.cost_per_step or 0) * steps
        cost += step_cost
        if spec.typical_time_months:
            time_months = max(time_months, spec.typical_time_months * steps)
        deltas.append(
            Delta(
                delta_id=f"{route_id}-d{i}",
                field=path,
                from_value=steps_to_raw(spec, f.x),
                to_value=steps_to_raw(spec, f.x + steps),
                from_steps=f.x,
                to_steps=f.x + steps,
                unit=spec.step.unit,
                derivation_of_current=fv[path].derivation,
                candidate_phrase=spec.candidate_phrase,
                typical_time_months=spec.typical_time_months,
                actionability=spec.actionability,
                cost=step_cost,
            )
        )
    return Route(
        route_id=route_id,
        deltas=deltas,
        cost=cost,
        # Conservative parallel assumption: the candidate works on all deltas at once,
        # so the route takes as long as its slowest single change.
        total_time_months=time_months,
        new_score=new_score,
        flip_test_passed=flip_ok,
    )


def _solver(job: JobTemplate, time_limit_s: float | None) -> cp_model.CpSolver:
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = float(
        time_limit_s if time_limit_s is not None else job.solver_time_limit_s
    )
    s.parameters.num_workers = 8
    s.parameters.random_seed = 0
    return s


def _partial_progress(
    fv: FeatureVector,
    job: JobTemplate,
    manifest: Manifest,
    *,
    tau: int,
    eps: int,
    rho: int,
    time_limit_s: float | None,
) -> Route | None:
    """The best the candidate can reach inside the horizon when nothing flips:
    maximise the (shrunk) score under the same constraints, minus the flip constraint,
    breaking ties toward the cheaper plan."""
    m = cp_model.CpModel()
    feats = _build_features(fv, job, manifest)
    _add_vars(m, feats)
    if not _add_structural_constraints(m, feats, job, manifest):
        return None
    cost_expr = sum(
        (f.spec.cost_per_step or 0) * f.a for f in feats.values() if f.movable
    )
    budget = 1 + sum(
        (f.spec.cost_per_step or 0) * f.max_a for f in feats.values() if f.movable
    )
    m.Maximize(_score_expr(feats, job, rho) * budget - cost_expr)
    s = _solver(job, time_limit_s)
    if s.Solve(m) not in _STATUS_OK:
        return None
    actions = {f.path: s.Value(f.a) for f in feats.values() if f.movable and s.Value(f.a) > 0}
    if not actions:
        return None
    return _make_route(
        "partial", fv, actions, feats, job, manifest,
        tau=tau, eps=eps, flip_required=False,
    )


def solve_recourse(
    fv: FeatureVector,
    job: JobTemplate,
    manifest: Manifest,
    *,
    tau: int,
    eps: int = 0,
    rho: int = 0,
    k: int | None = None,
    time_limit_s: float | None = None,
) -> list[Route] | NoFeasiblePath:
    """Return up to ``k`` support-disjoint minimum-cost routes to ``tau + eps``.

    Returns a :class:`NoFeasiblePath` when no route exists inside the horizon, or
    when a knockout sits on a feature the solver is not allowed to move.
    """
    k = k or job.k_routes
    current_score, _ = score_vector(fv, job, manifest)

    # Defensive: threshold_mode handles this case first, but a weighted-score
    # counterfactual while an immutable knockout is unmet would be a false statement.
    for ko in evaluate_knockouts(fv, job, manifest):
        if not ko.passed and not manifest.features[ko.path].solver_may_move:
            return NoFeasiblePath(
                reason="knockout_immutable",
                gap_remaining=max(0, tau + eps - current_score),
            )

    routes: list[Route] = []
    cuts: list[set[str]] = []
    for i in range(k):
        m = cp_model.CpModel()
        feats = _build_features(fv, job, manifest)
        _add_vars(m, feats)
        feasible = _add_structural_constraints(m, feats, job, manifest)
        if feasible:
            m.Add(_score_expr(feats, job, rho) >= tau + eps)
            for support in cuts:
                outside = [f.u for f in feats.values() if f.movable and f.path not in support]
                if not outside:
                    feasible = False
                    break
                m.Add(sum(outside) >= 1)
        if feasible:
            m.Minimize(
                sum((f.spec.cost_per_step or 0) * f.a for f in feats.values() if f.movable)
                + job.sparsity_lambda * sum(f.u for f in feats.values() if f.movable)
            )
            s = _solver(job, time_limit_s)
            feasible = s.Solve(m) in _STATUS_OK
        if not feasible:
            break
        actions = {
            f.path: s.Value(f.a) for f in feats.values() if f.movable and s.Value(f.a) > 0
        }
        routes.append(
            _make_route(
                f"r{i + 1}", fv, actions, feats, job, manifest,
                tau=tau, eps=eps, flip_required=True,
            )
        )
        cuts.append(set(actions))

    if routes:
        return routes
    return NoFeasiblePath(
        reason="no_path_within_horizon",
        gap_remaining=max(0, tau + eps - current_score),
        partial_progress=_partial_progress(
            fv, job, manifest, tau=tau, eps=eps, rho=rho, time_limit_s=time_limit_s
        ),
    )
