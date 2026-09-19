"""Mode B: the bar is set by the pool, not published in advance."""
from pathlib import Path

from recourse_screen.loaders import load_job, load_manifest, load_profile
from recourse_screen.recourse.ranking_mode import run_ranking_mode, score_pool
from recourse_screen.schemas import Envelope, Profile

FIXTURES = Path(__file__).parent / "fixtures"


def job_and_manifest():
    return (
        load_job(FIXTURES / "toy_job.yaml").model_copy(deep=True),
        load_manifest(FIXTURES / "toy_manifest.json"),
    )


def variant(projects: int) -> Profile:
    """Toy profile with a different backend project count. Score = 37 + 5 * projects."""
    profile = load_profile(FIXTURES / "toy_profile.json").model_copy(deep=True)
    profile.project_counts_by_topic["backend"] = projects
    return profile


def no_python(projects: int) -> Profile:
    """Same, but fails the `skills.python.months >= 24` knockout."""
    profile = variant(projects)
    profile.skills["python"].months = Envelope(value=6, derivation="computed", confidence="high")
    return profile


# candidate "c" scores 47; the pool runs 37, 57, 67, 77.
POOL_COUNTS = {"a": 0, "c": 2, "d": 4, "e": 6, "f": 8}


def pool() -> list[tuple[str, Profile]]:
    return [(cid, variant(n)) for cid, n in POOL_COUNTS.items()]


def test_score_pool_reports_score_and_knockout_status():
    job, manifest = job_and_manifest()
    rows = score_pool([*pool(), ("g", no_python(4))], job, manifest)
    assert rows == [
        ("a", 37, True), ("c", 47, True), ("d", 57, True),
        ("e", 67, True), ("f", 77, True), ("g", 39, False),  # losing the Python months costs 18 too
    ]


def test_rank_bar_and_threshold_for_a_rejected_candidate():
    job, manifest = job_and_manifest()
    outcome = run_ranking_mode(variant(2), job, manifest, pool(), "c", N=3)
    decision = outcome.decision
    assert decision.mode == "B"
    assert decision.score == 47
    assert decision.pool_size == 5 and decision.slots_n == 3
    assert decision.rank == 4  # 57, 67 and 77 are ahead
    # Bar = 3rd highest among the *other* members (57); beating it needs 58.
    assert decision.threshold == 58
    assert decision.passed is False
    assert outcome.aggregate_line == "3 of 5 advanced in this pool"


def test_a_top_n_candidate_passes_and_gets_no_routes():
    job, manifest = job_and_manifest()
    outcome = run_ranking_mode(variant(8), job, manifest, pool(), "f", N=3)
    assert outcome.decision.rank == 1
    assert outcome.decision.passed is True
    assert outcome.routes == []


def test_ties_are_resolved_against_the_candidate():
    job, manifest = job_and_manifest()
    twins = [("c", variant(2)), ("t1", variant(2)), ("t2", variant(2)), ("t3", variant(2))]
    outcome = run_ranking_mode(variant(2), job, manifest, twins, "c", N=3)
    assert outcome.decision.rank == 4  # three equal scores all count as ahead
    assert outcome.decision.threshold == 48  # strictly beating the bar of 47
    assert outcome.decision.passed is False


def test_routes_carry_the_rank_they_would_reach():
    job, manifest = job_and_manifest()
    outcome = run_ranking_mode(variant(2), job, manifest, pool(), "c", N=3)
    assert outcome.routes, "a feasible path to 58 exists inside the horizon"
    for route in outcome.routes:
        assert route.flip_test_passed is True
        assert route.new_score >= outcome.decision.threshold
        assert route.rank is not None and route.rank <= 3
    cheapest = outcome.routes[0]
    assert cheapest.cost == 14  # +1 backend project and the AWS certification
    assert cheapest.new_score == 59 and cheapest.rank == 3


def test_everyone_passes_when_the_pool_has_fewer_than_n_other_members():
    job, manifest = job_and_manifest()
    small = [("c", variant(2)), ("a", variant(0))]
    outcome = run_ranking_mode(variant(2), job, manifest, small, "c", N=3)
    assert outcome.decision.threshold == 0
    assert outcome.decision.rank == 1 and outcome.decision.passed is True
    assert outcome.routes == []


def test_members_failing_knockouts_rank_below_everyone_who_passes():
    job, manifest = job_and_manifest()
    # The candidate fails the Python knockout despite the highest raw score.
    mixed = [("c", no_python(8)), ("a", variant(0)), ("d", variant(4))]
    outcome = run_ranking_mode(no_python(8), job, manifest, mixed, "c", N=3)
    assert outcome.decision.knockouts_passed is False
    assert outcome.decision.rank == 3  # behind both qualified members
    assert outcome.decision.passed is False


def test_n_defaults_to_the_job_template():
    job, manifest = job_and_manifest()
    outcome = run_ranking_mode(variant(2), job, manifest, pool(), "c")
    assert outcome.decision.slots_n == job.mode.B.slots_N == 3
