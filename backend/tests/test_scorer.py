"""The additive scorer and the knockout conjunction that sits outside it."""
from pathlib import Path

import pytest

from recourse_screen.loaders import load_job, load_manifest, load_profile
from recourse_screen.schemas import Envelope, JobTemplate, ScoreTerm
from recourse_screen.score.features import ProtectedFeatureError, build_feature_vector
from recourse_screen.score.scorer import (
    evaluate_knockouts,
    make_decision,
    max_score,
    score_vector,
)

FIXTURES = Path(__file__).parent / "fixtures"


def toy():
    return (
        load_profile(FIXTURES / "toy_profile.json").model_copy(deep=True),
        load_job(FIXTURES / "toy_job.yaml").model_copy(deep=True),
        load_manifest(FIXTURES / "toy_manifest.json"),
    )


def test_toy_profile_scores_47():
    profile, job, manifest = toy()
    fv = build_feature_vector(profile, job, manifest)
    score, contributions = score_vector(fv, job, manifest)
    assert score == 47
    assert sum(c.contribution for c in contributions) == score
    assert {c.path: c.contribution for c in contributions} == {
        "skills.python.months": 18,
        "skills.django.months": 4,
        "project_counts_by_topic.backend": 10,
        "certifications.aws_saa": 0,
        "skills.docker.held": 6,
        "skills.sql.proficiency": 5,
        "education.highest_level": 4,
    }


def test_contributions_carry_the_candidate_phrase_and_headroom():
    profile, job, manifest = toy()
    fv = build_feature_vector(profile, job, manifest)
    _, contributions = score_vector(fv, job, manifest)
    sql = next(c for c in contributions if c.path == "skills.sql.proficiency")
    assert sql.phrase == "SQL proficiency"
    assert sql.cap == 3 and sql.max_contribution == 15


def test_cap_limits_the_contribution():
    profile, job, manifest = toy()
    job.score["skills.python.months"] = ScoreTerm(weight=6, cap=2)
    fv = build_feature_vector(profile, job, manifest)
    score, contributions = score_vector(fv, job, manifest)
    python = next(c for c in contributions if c.path == "skills.python.months")
    assert python.steps == 3 and python.contribution == 12  # capped at 2 steps
    assert score == 41


def test_knockout_on_months_passes():
    profile, job, manifest = toy()
    fv = build_feature_vector(profile, job, manifest)
    kos = evaluate_knockouts(fv, job, manifest)
    assert [(k.rule, k.passed, k.current_value) for k in kos] == [
        ("skills.python.months >= 24", True, 36)
    ]
    assert kos[0].actionability == "conditionally_actionable"


def test_knockout_fails_when_the_field_is_absent():
    profile, job, manifest = toy()
    profile.skills["python"].months = Envelope()  # absent
    fv = build_feature_vector(profile, job, manifest)
    ko = evaluate_knockouts(fv, job, manifest)[0]
    assert ko.passed is False and ko.current_value is None


def test_max_score():
    profile, job, manifest = toy()
    # 6*15 + 4*15 + 5*12 + 7*1 + 6*1 + 5*3 + 4*3
    assert max_score(job, manifest) == 250


def test_make_decision_rejects_below_threshold_and_ignores_the_margin():
    profile, job, manifest = toy()
    fv = build_feature_vector(profile, job, manifest)
    decision = make_decision(fv, job, manifest, mode="A", threshold=60, margin_eps=6)
    assert decision.passed is False
    assert decision.score == 47 and decision.knockouts_passed is True
    assert decision.threshold == 60 and decision.margin_eps == 6
    assert decision.max_score == 250

    # The margin is a solver target, never a stricter published bar.
    at_bar = make_decision(fv, job, manifest, mode="A", threshold=47, margin_eps=6)
    assert at_bar.passed is True


def test_a_failed_knockout_overrides_a_passing_score():
    profile, job, manifest = toy()
    profile.skills["python"].months = Envelope(value=6, derivation="computed", confidence="high")
    fv = build_feature_vector(profile, job, manifest)
    decision = make_decision(fv, job, manifest, mode="A", threshold=0)
    assert decision.score >= 0 and decision.knockouts_passed is False
    assert decision.passed is False


def test_protected_feature_never_reaches_the_scorer():
    profile = load_profile(FIXTURES / "toy_profile.json")
    manifest = load_manifest("data_science.json")
    job = JobTemplate(
        job_id="age_proxy", title="age proxy", family="software_engineering",
        manifest="data_science.json",
        score={"education.graduation_year": ScoreTerm(weight=1)},
        mode={"A": {"threshold": 1}, "B": {}},
    )
    with pytest.raises(ProtectedFeatureError):
        build_feature_vector(profile, job, manifest)
