"""Restatement channel: co-occurrence hints, and confirmations written back."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from recourse_screen import config
from recourse_screen.loaders import load_job, load_manifest
from recourse_screen.restate import NOT_MENTIONED, apply_confirmations, restatement_hints
from recourse_screen.schemas import Confirmation, Profile

FIXTURES = Path(__file__).parent / "fixtures"


def toy_profile(drop: tuple[str, ...] = ()) -> Profile:
    """The toy profile, optionally with some skills removed so they read absent."""
    data = json.loads((FIXTURES / "toy_profile.json").read_text())
    for skill in drop:
        data["skills"].pop(skill, None)
    return Profile.model_validate(data)


@pytest.fixture
def manifest():
    return load_manifest(config.MANIFEST_DIR / "data_science.json")


@pytest.fixture
def job():
    return load_job("data_scientist")


# --------------------------------------------------------------------------- #
# Hints
# --------------------------------------------------------------------------- #

def test_cooccurrence_hint_when_a_likely_skill_is_missing(manifest, job):
    # The fixture states Django but (in this variant) never mentions SQL.
    profile = toy_profile(drop=("sql",))
    hints = restatement_hints(profile, manifest, job)
    sql = next(h for h in hints if h.field == "skills.sql.held")
    assert sql.because_of == "django"
    assert sql.zero_cost is True
    assert sql.phrase


def test_no_cooccurrence_hint_when_the_skill_is_already_stated(manifest, job):
    # Unmodified fixture: SQL is stated, so there is nothing to restate.
    hints = restatement_hints(toy_profile(), manifest, job)
    assert all(h.field != "skills.sql.held" for h in hints)


def test_cooccurrence_hints_come_before_plain_absent_ones(manifest, job):
    hints = restatement_hints(toy_profile(drop=("sql",)), manifest, job)
    kinds = [h.because_of == NOT_MENTIONED for h in hints]
    assert kinds == sorted(kinds)  # False (co-occurrence) before True


def test_unmentioned_scored_paths_are_offered_as_hints(manifest, job):
    hints = {h.field: h for h in restatement_hints(toy_profile(), manifest, job)}
    assert hints["skills.statistics.held"].because_of == NOT_MENTIONED
    assert hints["derived.cloud_platform_held"].because_of == NOT_MENTIONED
    # Stated or computed fields are not offered: the screen already has them.
    assert "skills.docker.held" not in hints
    assert "education.highest_level" not in hints


def test_hints_never_offer_immutable_or_protected_paths(manifest, job):
    hints = restatement_hints(toy_profile(), manifest, job)
    fields = {h.field for h in hints}
    assert "eligibility.requires_sponsorship" not in fields
    assert not any(f.startswith("education.graduation_year") for f in fields)


def test_a_denied_field_is_never_offered_for_restatement(manifest, job):
    profile = toy_profile()
    profile.skills["statistics"] = profile.skills["docker"].model_copy(deep=True)
    profile.skills["statistics"].held.value = False
    profile.skills["statistics"].held.derivation = "denied"
    hints = restatement_hints(profile, manifest, job)
    assert all(h.field != "skills.statistics.held" for h in hints)


# --------------------------------------------------------------------------- #
# Confirmations
# --------------------------------------------------------------------------- #

def test_confirmation_is_marked_restated_and_recomputes_derived(manifest):
    profile = toy_profile()
    assert profile.derived == {}

    updated = apply_confirmations(profile, [Confirmation(path="skills.aws.held", value=True)],
                                  manifest)

    held = updated.resolve("skills.aws.held")
    assert held.value is True
    assert held.derivation == "restated"
    assert held.confidence == "high"
    cloud = updated.resolve("derived.cloud_platform_held")
    assert cloud.value is True
    assert cloud.derivation == "restated"


def test_confirmation_does_not_mutate_the_original_profile(manifest):
    profile = toy_profile()
    apply_confirmations(profile, [Confirmation(path="skills.aws.held", value=True)], manifest)
    assert "aws" not in profile.skills
    assert profile.derived == {}


def test_confirming_a_derived_boolean_directly_survives_recomputation(manifest):
    updated = apply_confirmations(
        toy_profile(), [Confirmation(path="derived.data_pipeline_held", value=True)], manifest)
    env = updated.resolve("derived.data_pipeline_held")
    assert env.value is True
    assert env.derivation == "restated"


def test_immutable_eligibility_path_is_refused(manifest):
    with pytest.raises(ValueError, match="immutable"):
        apply_confirmations(
            toy_profile(),
            [Confirmation(path="eligibility.requires_sponsorship", value=False)],
            manifest,
        )


def test_protected_path_is_refused(manifest):
    with pytest.raises(ValueError, match="protected"):
        apply_confirmations(
            toy_profile(), [Confirmation(path="education.graduation_year", value=2020)], manifest)


def test_unknown_path_is_refused(manifest):
    with pytest.raises(ValueError, match="not restatable"):
        apply_confirmations(
            toy_profile(), [Confirmation(path="skills.telepathy.held", value=True)], manifest)


def test_a_rejected_confirmation_applies_none_of_the_batch(manifest):
    profile = toy_profile()
    with pytest.raises(ValueError):
        apply_confirmations(
            profile,
            [Confirmation(path="skills.aws.held", value=True),
             Confirmation(path="eligibility.requires_sponsorship", value=False)],
            manifest,
        )
    assert "aws" not in profile.skills
