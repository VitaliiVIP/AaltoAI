"""Code-owned text: fallback sentences per derivation and unit, and framing."""
from __future__ import annotations

import pytest

from recourse_screen.explain.checker import check
from recourse_screen.explain.templates import (
    HUMAN_REVIEW_LINE,
    fallback_sentence,
    frame,
    full_fallback,
)
from recourse_screen.explain.whitelist import BlockerView, DeltaView, ExplanationInput


def dv(**kw) -> DeltaView:
    base = dict(
        delta_id="d1",
        field="derived.ml_framework_held",
        from_=None,
        to=True,
        unit="boolean",
        derivation_of_current="absent",
        candidate_phrase="hands-on experience with a machine-learning framework",
        typical_time_months=4,
        actionability="actionable",
        route_id="r1",
    )
    base.update(kw)
    return DeltaView(**base)


ABSENT_BOOL = dv()
STATED_MONTHS = dv(
    delta_id="d2", field="experience.data_months", from_=18, to=24, unit="months",
    derivation_of_current="computed", candidate_phrase="professional data science experience",
    typical_time_months=6, route_id="r1",
)
STATED_PROJECTS = dv(
    delta_id="d3", field="project_counts_by_topic.machine_learning", from_=1, to=2, unit="projects",
    derivation_of_current="stated", candidate_phrase="shipped machine-learning projects",
    typical_time_months=2, route_id="r2",
)
DENIED_BOOL = dv(
    delta_id="d4", field="derived.cloud_platform_held", from_=False, to=True, unit="boolean",
    derivation_of_current="denied",
    candidate_phrase="hands-on experience with a cloud platform (AWS, Azure or GCP)",
    typical_time_months=3, route_id="r2",
)
LEVEL_DEGREE = dv(
    delta_id="d5", field="education.highest_level", from_="bsc", to="msc", unit="level",
    derivation_of_current="stated", candidate_phrase="completed degree level",
    typical_time_months=24, route_id="r3",
)
LEVEL_INT = dv(
    delta_id="d6", field="skills.sql.proficiency", from_=1, to=2, unit="level",
    derivation_of_current="inferred", candidate_phrase="SQL proficiency",
    typical_time_months=None, route_id="r3",
)

ALL_DELTAS = [ABSENT_BOOL, STATED_MONTHS, STATED_PROJECTS, DENIED_BOOL, LEVEL_DEGREE, LEVEL_INT]


def make_input(deltas, **kw) -> ExplanationInput:
    base = dict(
        outcome="not_advanced",
        deltas=deltas,
        immutable_blockers=[],
        flip_test_passed=True,
        as_of="2026-09-19",
        model_version="screen-v1",
        mode="A",
    )
    base.update(kw)
    return ExplanationInput(**base)


# --------------------------------------------------------------------------- #
# Fallback sentences
# --------------------------------------------------------------------------- #

def test_absent_delta_is_a_question_not_an_accusation():
    s = fallback_sentence(ABSENT_BOOL)
    assert "did not mention" in s
    assert "if you have it, add it" in s
    # Never an assertion that the person lacks the skill.
    assert "you do not have" not in s.lower()
    assert "you lack" not in s.lower()


def test_absent_delta_without_a_time_figure_quotes_no_number():
    s = fallback_sentence(dv(typical_time_months=None))
    assert not any(ch.isdigit() for ch in s)


def test_stated_months_delta_uses_the_raw_magnitude():
    s = fallback_sentence(STATED_MONTHS)
    assert "6 more months" in s
    assert "professional data science experience" in s


def test_projects_delta_asks_for_one_more():
    s = fallback_sentence(STATED_PROJECTS)
    assert "one more" in s
    assert "shipped machine-learning projects" in s


def test_denied_delta_acknowledges_the_cv_said_no():
    s = fallback_sentence(DENIED_BOOL)
    assert "Your CV said you do not have" in s
    assert "3 months" in s


def test_level_delta_names_the_target_degree():
    s = fallback_sentence(LEVEL_DEGREE)
    assert "master's degree" in s
    assert "24 months" in s


def test_integer_level_delta_names_the_level():
    s = fallback_sentence(LEVEL_INT)
    assert "level 2" in s


@pytest.mark.parametrize("d", ALL_DELTAS, ids=lambda d: d.delta_id)
def test_every_fallback_sentence_passes_the_checker(d):
    input = make_input([d])
    assert check(full_fallback(input), input) == []


def test_full_fallback_covers_every_delta_once():
    input = make_input(ALL_DELTAS)
    sentences = full_fallback(input)
    assert [s.delta_id for s in sentences] == [d.delta_id for d in ALL_DELTAS]
    assert check(sentences, input) == []


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #

def test_frame_carries_every_required_disclosure():
    input = make_input(ALL_DELTAS)
    text = frame(input, full_fallback(input))
    assert "automated screen" in text
    assert "guidance, not a promise" in text
    assert "other changes could also have been enough" in text
    assert "typical, not exact" in text
    assert HUMAN_REVIEW_LINE in text


def test_frame_is_exactly_two_paragraphs():
    input = make_input(ALL_DELTAS)
    text = frame(input, full_fallback(input))
    assert len(text.split("\n\n")) == 2


def test_frame_uses_only_the_cheapest_route():
    # ALL_DELTAS spans routes r1 (ABSENT_BOOL, STATED_MONTHS), r2 (STATED_PROJECTS,
    # DENIED_BOOL) and r3 (LEVEL_DEGREE, LEVEL_INT). The email is one route, not
    # a menu of alternatives, so only r1's content should show up.
    input = make_input(ALL_DELTAS)
    text = frame(input, full_fallback(input))
    assert fallback_sentence(ABSENT_BOOL) in text
    assert fallback_sentence(STATED_MONTHS) in text
    assert fallback_sentence(STATED_PROJECTS) not in text
    assert fallback_sentence(LEVEL_DEGREE) not in text
    assert "Route 1" not in text


def test_frame_never_claims_an_interview_and_gives_no_score():
    input = make_input(ALL_DELTAS, mode="B", rank=7, pool_size=24, slots_n=3,
                       route_ranks={"r1": 2, "r2": 3, "r3": 5})
    text = frame(input, full_fallback(input))
    lowered = text.lower()
    assert "interview" not in lowered
    assert "threshold" not in lowered
    assert "score" not in lowered


def test_mode_b_reports_rank_and_the_aggregate_line():
    input = make_input(ALL_DELTAS, mode="B", rank=7, pool_size=24, slots_n=3,
                       route_ranks={"r1": 2, "r2": 3, "r3": 5})
    text = frame(input, full_fallback(input))
    assert "You placed 7 of 24 in this pool." in text
    assert "3 of 24 advanced." in text


def test_mode_a_says_nothing_about_a_pool():
    text = frame(make_input(ALL_DELTAS), full_fallback(make_input(ALL_DELTAS)))
    assert "pool" not in text.lower()


def test_immutable_blocker_disclosure_is_verbatim():
    disclosure = ("This role requires the right to work without sponsorship; this is a "
                  "legal eligibility requirement.")
    input = make_input(
        [ABSENT_BOOL],
        immutable_blockers=[BlockerView(field="eligibility.requires_sponsorship",
                                        disclosure=disclosure)],
    )
    text = frame(input, full_fallback(input))
    assert disclosure in text
    assert "no action on your part can change it" in text


def test_no_feasible_path_says_so_plainly_and_offers_human_review():
    input = make_input([STATED_MONTHS], flip_test_passed=False, no_feasible_path=True,
                       partial_route_id="r1")
    text = frame(input, full_fallback(input))
    assert "did not find any combination of changes" in text
    assert "would not have changed this decision" in text
    assert HUMAN_REVIEW_LINE in text
    # It must not also claim the listed steps are a sufficient path.
    assert "one sufficient path" not in text


def test_explanation_with_no_deltas_still_frames_the_disclosures():
    input = make_input([], flip_test_passed=False)
    text = frame(input, [])
    assert "automated screen" in text
    assert HUMAN_REVIEW_LINE in text
