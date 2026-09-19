"""Aggregation of solver outcomes, exercised with fake RecourseOutcome-shaped
objects. No CP-SAT here: this file must stay fast and must not depend on the
solver being finished."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from recourse_screen.eval.recourse_metrics import summarise_outcomes


@dataclass
class FakeDelta:
    field: str


@dataclass
class FakeRoute:
    deltas: list[FakeDelta]
    cost: int
    new_score: int
    flip_test_passed: bool = True


@dataclass
class FakeDecision:
    passed: bool
    score: int
    threshold: int
    rank: int | None = None


@dataclass
class FakeOutcome:
    decision: FakeDecision
    routes: list[FakeRoute] = field(default_factory=list)
    immutable_blockers: list[Any] = field(default_factory=list)
    no_feasible_path: Any = None


def _route(fields: list[str], cost: int, new_score: int, flip: bool = True) -> FakeRoute:
    return FakeRoute(deltas=[FakeDelta(f) for f in fields], cost=cost, new_score=new_score,
                     flip_test_passed=flip)


PASSED = FakeOutcome(decision=FakeDecision(passed=True, score=72, threshold=60))
TWO_ROUTES = FakeOutcome(
    decision=FakeDecision(passed=False, score=48, threshold=60),
    routes=[_route(["skills.kubernetes.held", "skills.docker.held"], 10, 62),
            _route(["skills.kubernetes.held", "derived.iac_held"], 14, 64)],
)
SHORT_ROUTE = FakeOutcome(  # solver says the flip passed but the score does not clear the bar
    decision=FakeDecision(passed=False, score=40, threshold=60),
    routes=[_route(["derived.sql_held"], 7, 55)],
)
BLOCKED = FakeOutcome(
    decision=FakeDecision(passed=False, score=20, threshold=60),
    immutable_blockers=[{"field": "eligibility.requires_sponsorship"}],
    no_feasible_path={"reason": "gap_exceeds_horizon", "gap_remaining": 18},
)

CORPUS = [PASSED, TWO_ROUTES, SHORT_ROUTE, BLOCKED]
IDS = ["c1", "c2", "c3", "c4"]


@pytest.fixture(scope="module")
def s():
    return summarise_outcomes(CORPUS, mode="A", ids=IDS)


def test_pass_rate_and_counts(s):
    assert s["mode"] == "A"
    assert s["n_candidates"] == 4 and s["n_passed"] == 1 and s["n_rejected"] == 3
    assert s["pass_rate"] == pytest.approx(0.25)


def test_validity_rechecks_the_score_against_the_threshold(s):
    # three routes among rejected candidates; the 55-point one does not clear 60
    assert s["n_routes"] == 3
    assert s["validity"] == pytest.approx(2 / 3)
    assert s["validity_per_candidate"] == pytest.approx(0.5)


def test_a_failed_flip_test_is_invalid_even_with_a_high_score():
    lying = FakeOutcome(decision=FakeDecision(passed=False, score=40, threshold=60),
                        routes=[_route(["skills.docker.held"], 3, 99, flip=False)])
    out = summarise_outcomes([lying], mode="A", ids=["x"])
    assert out["validity"] == pytest.approx(0.0)
    assert out["actionability_rate"] == pytest.approx(1.0)  # a route exists, it is just not valid


def test_actionability_sparsity_and_cost(s):
    assert s["actionability_rate"] == pytest.approx(2 / 3)
    assert s["l0_mean"] == pytest.approx(5 / 3)  # 2, 2, 1
    assert s["l0_max"] == 2
    assert s["cost_median"] == pytest.approx(10.0)  # 7, 10, 14
    assert s["cost_mean"] == pytest.approx(31 / 3)
    assert s["cheapest_route_cost_median"] == pytest.approx(8.5)  # 10 and 7


def test_diversity_counts_distinct_support_sets(s):
    assert s["diversity_mean_distinct_supports"] == pytest.approx(1.5)  # 2 and 1


def test_duplicate_routes_have_no_diversity():
    dup = FakeOutcome(decision=FakeDecision(passed=False, score=40, threshold=60),
                      routes=[_route(["a", "b"], 5, 61), _route(["b", "a"], 6, 62)])
    out = summarise_outcomes([dup], mode="A", ids=["x"])
    assert out["diversity_mean_distinct_supports"] == pytest.approx(1.0)


def test_blocker_and_no_path_rates(s):
    assert s["immutable_blocker_rate"] == pytest.approx(1 / 3)
    assert s["no_feasible_path_rate"] == pytest.approx(1 / 3)


def test_per_candidate_table_covers_rejected_candidates_only(s):
    rows = {r["candidate_id"]: r for r in s["per_candidate"]}
    assert set(rows) == {"c2", "c3", "c4"}
    assert rows["c2"]["all_routes_valid"] is True
    assert rows["c3"]["all_routes_valid"] is False
    assert rows["c4"]["no_feasible_path"] is True and rows["c4"]["immutable_blockers"] == 1
    assert rows["c2"]["l0"] == [2, 2] and rows["c2"]["cost"] == [10, 14]


def test_mode_b_uses_the_bar_score_as_the_threshold():
    below = FakeOutcome(decision=FakeDecision(passed=False, score=50, threshold=71, rank=8),
                        routes=[_route(["skills.kubernetes.held"], 9, 70)])
    above = FakeOutcome(decision=FakeDecision(passed=False, score=50, threshold=71, rank=8),
                        routes=[_route(["skills.kubernetes.held"], 9, 71)])
    assert summarise_outcomes([below], mode="B", ids=["x"])["validity"] == pytest.approx(0.0)
    assert summarise_outcomes([above], mode="B", ids=["y"])["validity"] == pytest.approx(1.0)
    assert summarise_outcomes([above], mode="B", ids=["y"])["per_candidate"][0]["rank"] == 8


def test_ids_must_line_up():
    with pytest.raises(ValueError):
        summarise_outcomes(CORPUS, mode="A", ids=["only-one"])


def test_empty_corpus_is_all_zeroes():
    out = summarise_outcomes([], mode="A", ids=[])
    assert out["n_candidates"] == 0 and out["pass_rate"] == 0.0
    assert out["l0_mean"] is None and out["cost_median"] is None
    assert out["per_candidate"] == []


def test_all_passed_corpus_has_no_rejected_denominators():
    out = summarise_outcomes([PASSED, PASSED], mode="A", ids=["a", "b"])
    assert out["pass_rate"] == pytest.approx(1.0)
    assert out["actionability_rate"] == 0.0 and out["validity"] == 0.0
