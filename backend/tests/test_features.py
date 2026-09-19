"""Feature projection: raw profile values -> integer solver steps."""
from pathlib import Path

import pytest

from recourse_screen.loaders import load_job, load_manifest, load_profile, manifest_for_job
from recourse_screen.schemas import Envelope, JobTemplate, ScoreTerm
from recourse_screen.score.features import (
    ProtectedFeatureError,
    build_feature_vector,
    job_feature_paths,
    raw_to_steps,
    steps_to_raw,
)

FIXTURES = Path(__file__).parent / "fixtures"


def toy():
    return (
        load_profile(FIXTURES / "toy_profile.json").model_copy(deep=True),
        load_job(FIXTURES / "toy_job.yaml").model_copy(deep=True),
        load_manifest(FIXTURES / "toy_manifest.json"),
    )


def test_steps_match_the_worked_example():
    profile, job, manifest = toy()
    fv = build_feature_vector(profile, job, manifest)
    assert {p: v.steps for p, v in fv.items()} == {
        "skills.python.months": 3,  # 36 months / 12
        "skills.django.months": 1,
        "project_counts_by_topic.backend": 2,
        "certifications.aws_saa": 0,
        "skills.docker.held": 1,
        "skills.sql.proficiency": 1,
        "education.highest_level": 1,  # index of "bsc" in the ladder
    }
    assert fv["skills.python.months"].raw_value == 36
    assert fv["skills.docker.held"].raw_value is True
    assert fv["education.highest_level"].derivation == "stated"


def test_months_use_the_step_size_and_clamp_to_the_domain():
    manifest = load_manifest(FIXTURES / "toy_manifest.json")
    spec = manifest.features["skills.python.months"]  # size 12, domain_max 15
    assert raw_to_steps(spec, 36) == 3
    assert raw_to_steps(spec, 35) == 2  # floor, never round up
    assert raw_to_steps(spec, None) == 0
    assert raw_to_steps(spec, 9999) == 15
    assert steps_to_raw(spec, 3) == 36


def test_bool_and_ordinal_roundtrip():
    manifest = load_manifest(FIXTURES / "toy_manifest.json")
    bool_spec = manifest.features["skills.docker.held"]
    ord_spec = manifest.features["education.highest_level"]
    assert raw_to_steps(bool_spec, True) == 1
    assert raw_to_steps(bool_spec, False) == 0
    assert steps_to_raw(bool_spec, 1) is True
    assert raw_to_steps(ord_spec, "msc") == 2
    assert raw_to_steps(ord_spec, "unheard_of") == 0
    assert steps_to_raw(ord_spec, 2) == "msc"


def test_job_feature_paths_include_knockout_and_dependency_only_features():
    job = load_job("backend_engineer")
    manifest = manifest_for_job(job)
    paths = job_feature_paths(job, manifest)
    assert "skills.python.held" in paths  # knockout only
    assert "experience.software_months" in paths  # knockout only
    assert paths[: len(job.score)] == list(job.score)


def test_absent_prior_credits_steps_but_leaves_the_raw_value_alone():
    profile, job, manifest = toy()
    job.score["certifications.aws_saa"] = ScoreTerm(weight=7, absent_prior=1)
    fv = build_feature_vector(profile, job, manifest)
    cert = fv["certifications.aws_saa"]
    assert cert.steps == 1 and cert.prior_applied is True
    assert cert.raw_value is False  # the prior scores; it does not assert the fact


def test_denied_never_earns_a_prior():
    profile, job, manifest = toy()
    job.score["skills.docker.held"] = ScoreTerm(weight=6, absent_prior=1)
    profile.skills["docker"].held = Envelope(value=False, derivation="denied", confidence="high")
    fv = build_feature_vector(profile, job, manifest)
    assert fv["skills.docker.held"].steps == 0
    assert fv["skills.docker.held"].prior_applied is False


def test_protected_feature_is_refused():
    profile = load_profile(FIXTURES / "toy_profile.json")
    manifest = load_manifest("software_engineering.json")
    job = JobTemplate(
        job_id="bad", title="bad", family="software_engineering",
        manifest="software_engineering.json",
        score={"education.graduation_year": ScoreTerm(weight=1)},
        mode={"A": {"threshold": 1}, "B": {}},
    )
    with pytest.raises(ProtectedFeatureError, match="education.graduation_year"):
        build_feature_vector(profile, job, manifest)


def test_unknown_path_raises_key_error():
    profile, job, manifest = toy()
    job.score["skills.cobol.months"] = ScoreTerm(weight=1)
    with pytest.raises(KeyError, match="skills.cobol.months"):
        build_feature_vector(profile, job, manifest)
