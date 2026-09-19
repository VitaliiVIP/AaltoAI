"""CP-SAT recourse solver, checked against the worked example in
research/notes/recourse_engine_brief.md section 5 (support-disjoint diversity)."""
from pathlib import Path

from recourse_screen.loaders import load_job, load_manifest, load_profile
from recourse_screen.recourse.solver import solve_recourse
from recourse_screen.recourse.threshold_mode import run_threshold_mode
from recourse_screen.schemas import (
    Education,
    Eligibility,
    Envelope,
    Experience,
    NoFeasiblePath,
    Profile,
    Provenance,
    Route,
    SkillEntry,
)
from recourse_screen.score.features import build_feature_vector
from recourse_screen.score.scorer import score_vector

FIXTURES = Path(__file__).parent / "fixtures"


def toy():
    return (
        load_profile(FIXTURES / "toy_profile.json").model_copy(deep=True),
        load_job(FIXTURES / "toy_job.yaml").model_copy(deep=True),
        load_manifest(FIXTURES / "toy_manifest.json"),
    )


def toy_fv():
    profile, job, manifest = toy()
    return build_feature_vector(profile, job, manifest), job, manifest


def actions(route: Route) -> dict[str, int]:
    return {d.field: d.to_steps - d.from_steps for d in route.deltas}


# --------------------------------------------------------------------------- #
# The worked example
# --------------------------------------------------------------------------- #


def test_baseline_is_47_with_a_gap_of_13():
    fv, job, manifest = toy_fv()
    score, _ = score_vector(fv, job, manifest)
    assert score == 47
    assert job.mode.A.threshold - score == 13


def test_three_support_disjoint_routes_at_eps_zero():
    fv, job, manifest = toy_fv()
    routes = solve_recourse(fv, job, manifest, tau=60, eps=0)
    assert [r.cost for r in routes] == [16, 19, 21]
    assert [r.new_score for r in routes] == [62, 64, 64]
    assert [actions(r) for r in routes] == [
        {"project_counts_by_topic.backend": 2, "skills.sql.proficiency": 1},
        {"certifications.aws_saa": 1, "project_counts_by_topic.backend": 2},
        {"certifications.aws_saa": 1, "skills.sql.proficiency": 2},
    ]
    assert [r.route_id for r in routes] == ["r1", "r2", "r3"]


def test_robustness_margin_raises_the_price_of_the_cheapest_path():
    fv, job, manifest = toy_fv()
    routes = solve_recourse(fv, job, manifest, tau=60, eps=6)
    assert [r.cost for r in routes] == [22, 25, 27]
    assert all(r.new_score >= 66 for r in routes)


def test_every_route_passes_the_flip_test():
    fv, job, manifest = toy_fv()
    for eps in (0, 6):
        for route in solve_recourse(fv, job, manifest, tau=60, eps=eps):
            assert route.flip_test_passed is True
            assert route.new_score >= 60 + eps


def test_docker_is_never_proposed_because_it_is_already_held():
    fv, job, manifest = toy_fv()
    assert fv["skills.docker.held"].steps == 1
    for eps in (0, 6):
        for route in solve_recourse(fv, job, manifest, tau=60, eps=eps):
            assert "skills.docker.held" not in actions(route)


def test_education_is_never_proposed_because_it_is_dominated():
    fv, job, manifest = toy_fv()
    for eps in (0, 6):
        for route in solve_recourse(fv, job, manifest, tau=60, eps=eps):
            assert "education.highest_level" not in actions(route)


def test_each_route_touches_a_feature_no_earlier_route_touched():
    fv, job, manifest = toy_fv()
    routes = solve_recourse(fv, job, manifest, tau=60, eps=0)
    supports = [set(actions(r)) for r in routes]
    for i, support in enumerate(supports):
        for earlier in supports[:i]:
            assert support - earlier, (
                f"{routes[i].route_id} is a near-duplicate of an earlier route"
            )


def test_routes_carry_presentable_delta_metadata():
    fv, job, manifest = toy_fv()
    route = solve_recourse(fv, job, manifest, tau=60, eps=0)[0]
    projects = next(d for d in route.deltas if d.field == "project_counts_by_topic.backend")
    assert (projects.from_value, projects.to_value) == (2, 4)
    assert projects.unit == "projects"
    assert projects.candidate_phrase == "backend projects"
    assert projects.derivation_of_current == "computed"
    assert projects.cost == 10
    assert route.cost == sum(d.cost for d in route.deltas)
    assert len({d.delta_id for d in route.deltas}) == len(route.deltas)


def test_total_time_is_the_slowest_single_change():
    profile, job, manifest = toy()
    manifest = manifest.model_copy(deep=True)
    manifest.features["project_counts_by_topic.backend"].typical_time_months = 2
    manifest.features["skills.sql.proficiency"].typical_time_months = 3
    fv = build_feature_vector(profile, job, manifest)
    route = solve_recourse(fv, job, manifest, tau=60, eps=0)[0]
    # +2 projects at 2 months each = 4; +1 SQL level = 3; done in parallel => 4.
    assert route.total_time_months == 4


# --------------------------------------------------------------------------- #
# Constraints
# --------------------------------------------------------------------------- #


def test_delta_dependency_caps_extra_projects_without_extra_python():
    fv, job, manifest = toy_fv()
    for eps in (0, 6):
        for route in solve_recourse(fv, job, manifest, tau=60, eps=eps):
            acts = actions(route)
            assert acts.get("project_counts_by_topic.backend", 0) <= 2 + 2 * acts.get(
                "skills.python.months", 0
            )


def test_level_dependency_forces_the_prerequisite_to_move_too():
    profile, job, manifest = toy()
    job.score = {
        k: v for k, v in job.score.items()
        if k in ("skills.django.months", "skills.python.months")
    }
    job.score["skills.django.months"].weight = 10
    job.score["skills.python.months"].weight = 1
    fv = build_feature_vector(profile, job, manifest)

    routes = solve_recourse(fv, job, manifest, tau=43, k=1)
    acts = actions(routes[0])
    # Django can only reach 4 years if Python reaches 4 years: x'[django] <= x'[python].
    assert acts["skills.django.months"] == 3
    assert acts["skills.python.months"] == 1
    django = next(d for d in routes[0].deltas if d.field == "skills.django.months")
    python = next(d for d in routes[0].deltas if d.field == "skills.python.months")
    assert django.to_steps <= python.to_steps


def test_a_feature_at_its_cap_is_frozen():
    profile, job, manifest = toy()
    job.score["skills.sql.proficiency"].cap = 1  # candidate is already at 1
    fv = build_feature_vector(profile, job, manifest)
    for route in solve_recourse(fv, job, manifest, tau=60, eps=0):
        assert "skills.sql.proficiency" not in actions(route)


def test_weight_shrink_makes_recourse_more_expensive():
    fv, job, manifest = toy_fv()
    plain = solve_recourse(fv, job, manifest, tau=60, k=1)
    robust = solve_recourse(fv, job, manifest, tau=60, rho=1, k=1)
    assert robust[0].cost > plain[0].cost


# --------------------------------------------------------------------------- #
# Infeasibility
# --------------------------------------------------------------------------- #


def test_no_path_within_the_horizon_returns_partial_progress():
    fv, job, manifest = toy_fv()
    result = solve_recourse(fv, job, manifest, tau=150)
    assert isinstance(result, NoFeasiblePath)
    assert result.reason == "no_path_within_horizon"
    assert result.gap_remaining == 103
    partial = result.partial_progress
    assert partial is not None
    assert partial.flip_test_passed is False
    assert partial.new_score == 128  # the ceiling inside the 18-month horizon
    assert partial.new_score < 150


def test_nothing_to_offer_gives_no_partial_progress():
    profile, job, manifest = toy()
    manifest = manifest.model_copy(deep=True)
    for spec in manifest.features.values():
        spec.max_delta = 0
    fv = build_feature_vector(profile, job, manifest)
    result = solve_recourse(fv, job, manifest, tau=150)
    assert isinstance(result, NoFeasiblePath)
    assert result.partial_progress is None


# --------------------------------------------------------------------------- #
# Immutable knockouts, against the real manifest
# --------------------------------------------------------------------------- #


def sponsorship_profile() -> Profile:
    return Profile(
        as_of="2026-09-19",
        provenance=Provenance(
            cv_sha256="fixture", extractor_model="fixture", prompt_version="fixture",
            taxonomy_version="fixture", extracted_at="2026-09-19T00:00:00Z",
        ),
        experience=Experience(
            software_months=Envelope(value=48, derivation="computed", confidence="high"),
            backend_months=Envelope(value=36, derivation="computed", confidence="high"),
        ),
        skills={
            "python": SkillEntry(
                held=Envelope(value=True, derivation="stated", confidence="high"),
                months=Envelope(value=36, derivation="computed", confidence="high"),
            ),
            "docker": SkillEntry(held=Envelope(value=True, derivation="stated", confidence="high")),
        },
        education=Education(
            highest_level=Envelope(value="bsc", derivation="stated", confidence="high")
        ),
        eligibility=Eligibility(
            requires_sponsorship=Envelope(value=True, derivation="stated", confidence="high")
        ),
    )


def sponsorship_job():
    job = load_job("backend_engineer").model_copy(deep=True)
    job.knockouts = [*job.knockouts, "eligibility.requires_sponsorship == false"]
    return job


def test_solver_refuses_to_trade_around_an_immutable_knockout():
    job = sponsorship_job()
    manifest = load_manifest("software_engineering.json")
    fv = build_feature_vector(sponsorship_profile(), job, manifest)
    result = solve_recourse(fv, job, manifest, tau=60)
    assert isinstance(result, NoFeasiblePath)
    assert result.reason == "knockout_immutable"


def test_threshold_mode_reports_the_blocker_instead_of_a_false_counterfactual():
    job = sponsorship_job()
    manifest = load_manifest("software_engineering.json")
    outcome = run_threshold_mode(sponsorship_profile(), job, manifest)
    assert outcome.decision.passed is False
    assert outcome.routes == []
    assert outcome.no_feasible_path is None
    assert [b.field for b in outcome.immutable_blockers] == ["eligibility.requires_sponsorship"]
    assert "sponsorship" in outcome.immutable_blockers[0].disclosure


def test_threshold_mode_on_the_toy_job():
    profile, job, manifest = toy()
    outcome = run_threshold_mode(profile, job, manifest)
    assert outcome.decision.passed is False
    assert outcome.decision.score == 47
    assert [r.cost for r in outcome.routes] == [16, 19, 21]
    assert outcome.immutable_blockers == []
    assert outcome.assertions["protected_excluded_solver"] is True


def test_threshold_mode_returns_no_routes_when_the_candidate_passes():
    profile, job, manifest = toy()
    job.mode.A.threshold = 40
    outcome = run_threshold_mode(profile, job, manifest)
    assert outcome.decision.passed is True
    assert outcome.routes == []
    assert outcome.no_feasible_path is None
