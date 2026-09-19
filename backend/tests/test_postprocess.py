"""Unit tests for the extraction post-processing. No API calls anywhere in here.

The fixtures build real `ExtractionOutput` instances (the same dynamically-built model
the LLM fills in), so the tests also pin the schema the prompt depends on.
"""
from __future__ import annotations

import pytest

from recourse_screen.dates import union_months
from recourse_screen.loaders import load_manifest, load_taxonomy
from recourse_screen.extract import prompts
from recourse_screen.extract.postprocess import (
    ProtectedFieldError,
    QuoteIndex,
    build_profile,
    infer_seniority,
    normalise_roles,
    scrub,
    skill_months,
    verification_stats,
    verify_evidence,
    verify_role_evidence,
)
from recourse_screen.schemas import Envelope, Evidence, Provenance, SkillEntry

AS_OF = "2026-09-19"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


@pytest.fixture(scope="module")
def manifest():
    return load_manifest("software_engineering.json")


@pytest.fixture(scope="module")
def output_model(taxonomy):
    return prompts.extraction_model_for(taxonomy)


def make_provenance() -> Provenance:
    return Provenance(
        cv_sha256="0" * 64,
        source_file="test_cv.txt",
        extractor_model="claude-opus-5",
        prompt_version="extract-test",
        taxonomy_version="swe-core-0.1",
        extracted_at="2026-09-19T00:00:00+00:00",
    )


def role_dict(**overrides):
    base = {
        "title_raw": "Backend Developer",
        "title_canonical": "backend_engineer",
        "employer": "FinServ Digital",
        "start_raw": "2022",
        "end_raw": "2026",
        "is_backend_role": True,
        "skills_mentioned": ["python"],
        "primary_skills": ["python"],
        "quote": "Backend Developer, FinServ Digital (2022-2026)",
    }
    base.update(overrides)
    return base


def extraction(output_model, **overrides):
    base = {
        "roles": [],
        "skills_block": [],
        "denied_skills": [],
        "projects": [],
        "education": {"highest_level": "not_stated", "field": "",
                      "in_progress": "unclear", "quote": ""},
        "certifications": [],
        "languages": [],
        "eligibility": {
            "work_authorization_region": "", "requires_sponsorship": "unclear",
            "location_country": "", "relocation_willing": "unclear", "quote": "",
        },
        "unmatched_skills": [],
        "never_extract_ack": [],
    }
    base.update(overrides)
    return output_model.model_validate(base)


# --------------------------------------------------------------------------- #
# date normalisation on the demo formats
# --------------------------------------------------------------------------- #

def test_year_only_range_is_split_and_gets_year_precision(output_model):
    """'(2020-2026)' arrives split by the model; both ends land mid-year."""
    raw = extraction(output_model, roles=[role_dict(start_raw="2020", end_raw="2026")])
    role = normalise_roles(raw.roles, as_of=AS_OF)[0]
    assert (role.start, role.end) == ("2020-07", "2026-07")
    assert role.date_precision == "year"
    assert role.months == 72


def test_present_resolves_to_as_of_never_the_clock(output_model):
    raw = extraction(output_model, roles=[role_dict(start_raw="Aug 2025", end_raw="present")])
    role = normalise_roles(raw.roles, as_of=AS_OF)[0]
    assert (role.start, role.end) == ("2025-08", "2026-09")
    assert role.date_precision == "month"
    assert role.months == 13


def test_month_range_with_full_month_names(output_model):
    raw = extraction(output_model,
                     roles=[role_dict(start_raw="May 2026", end_raw="August 2026")])
    role = normalise_roles(raw.roles, as_of=AS_OF)[0]
    assert (role.start, role.end) == ("2026-05", "2026-08")
    assert role.date_precision == "month"
    assert role.months == 3


def test_end_after_as_of_is_clamped(output_model):
    raw = extraction(output_model, roles=[role_dict(start_raw="2026-01", end_raw="2027-12")])
    role = normalise_roles(raw.roles, as_of=AS_OF)[0]
    assert role.end == "2026-09"
    assert role.months == 8


def test_unparsable_start_leaves_duration_unknown_not_zero(output_model):
    raw = extraction(output_model, roles=[role_dict(start_raw="", end_raw="")])
    role = normalise_roles(raw.roles, as_of=AS_OF)[0]
    assert role.start is None and role.end is None
    assert role.months is None
    assert role.date_precision == "unknown"


def test_mixed_precision_endpoints_degrade_to_year(output_model):
    raw = extraction(output_model, roles=[role_dict(start_raw="Mar 2022", end_raw="2026")])
    role = normalise_roles(raw.roles, as_of=AS_OF)[0]
    assert role.date_precision == "year"


# --------------------------------------------------------------------------- #
# interval union
# --------------------------------------------------------------------------- #

def test_overlapping_roles_union_not_sum(output_model):
    """A freelance contract overlapping a full-time job must be counted once."""
    raw = extraction(output_model, roles=[
        role_dict(start_raw="2020-01", end_raw="2024-01", employer="Day Job"),
        role_dict(start_raw="2022-01", end_raw="2026-01", employer="Freelance"),
    ])
    roles = normalise_roles(raw.roles, as_of=AS_OF)
    assert [r.months for r in roles] == [48, 48]
    assert skill_months(roles, "python") == 72  # union, not the 96 a sum would give


def test_skill_months_only_counts_roles_that_mention_it(output_model):
    raw = extraction(output_model, roles=[
        role_dict(start_raw="2020-01", end_raw="2024-01", skills_mentioned=["python"]),
        role_dict(start_raw="2024-01", end_raw="2026-01", skills_mentioned=["java"],
                  primary_skills=["java"]),
    ])
    roles = normalise_roles(raw.roles, as_of=AS_OF)
    assert skill_months(roles, "python") == 48
    assert skill_months(roles, "java") == 24
    assert skill_months(roles, "kubernetes") is None


def test_disjoint_intervals_add_up():
    assert union_months([("2020-01", "2021-01"), ("2022-01", "2023-01")]) == 24


# --------------------------------------------------------------------------- #
# evidence verification
# --------------------------------------------------------------------------- #

CV = """Experience
Backend Developer, FinServ Digital (2022-2026)
- Built Python services deployed on AWS ECS (not Kubernetes)

Skills
Python, AWS ECS, Docker
"""


def test_quote_index_exact_and_whitespace_normalised_hits():
    index = QuoteIndex("Embedded Software Engineer          Aug 2025-Present")
    assert index.find("Embedded Software Engineer") == (0, 26)
    # collapsed whitespace and an en dash the model substituted for a hyphen
    span = index.find("Embedded Software Engineer Aug 2025–Present")
    assert span is not None and span[0] == 0
    assert index.find("Principal Architect") is None


def test_failing_quote_lowers_confidence_but_keeps_the_value(output_model, manifest, taxonomy):
    raw = extraction(output_model, roles=[role_dict()], skills_block=[
        {"skill": "docker", "quote": "Docker"},
    ])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    profile.skills["docker"].held.confidence = "high"
    profile.skills["docker"].held.evidence = [Evidence(quote="Rust, Haskell, Erlang")]
    verify_evidence(profile, CV)
    assert profile.skills["docker"].held.value is True
    assert profile.skills["docker"].held.derivation == "stated"
    assert profile.skills["docker"].held.confidence == "low"
    assert profile.skills["docker"].held.evidence[0].verified is False


def test_failing_quote_on_a_knockout_field_drops_the_value(output_model, manifest, taxonomy):
    raw = extraction(output_model, roles=[role_dict()])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    assert profile.skills["python"].held.value is True
    profile.skills["python"].held.evidence = [Evidence(quote="Expert Python, 30 years")]
    verify_evidence(profile, CV)
    assert profile.skills["python"].held.value is None
    assert profile.skills["python"].held.derivation == "absent"
    assert profile.skills["python"].held.confidence == "low"


def test_unverifiable_role_loses_its_dates(output_model):
    raw = extraction(output_model, roles=[
        role_dict(quote="Backend Developer, FinServ Digital (2022-2026)"),
        role_dict(quote="Chief Architect, Fictional Oy (2010-2026)", employer="Fictional Oy"),
    ])
    roles = verify_role_evidence(normalise_roles(raw.roles, as_of=AS_OF), QuoteIndex(CV))
    assert roles[0].months == 48 and roles[0].evidence[0].verified is True
    assert roles[1].months is None and roles[1].start is None
    assert roles[1].date_precision == "unknown"
    assert roles[1].evidence[0].verified is False


def test_verification_stats_counts_every_quote(output_model, manifest, taxonomy):
    raw = extraction(output_model, roles=[role_dict()], skills_block=[
        {"skill": "docker", "quote": "Docker"},
        {"skill": "rust", "quote": "Rust (10 years)"},
    ])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    stats = verification_stats(profile)
    assert stats["total"] > 0
    assert stats["verified"] == stats["total"] - 1
    assert any("Rust (10 years)" in f for f in stats["failures"])


# --------------------------------------------------------------------------- #
# the protected scrub
# --------------------------------------------------------------------------- #

def test_scrub_passes_on_a_clean_profile(output_model, manifest, taxonomy):
    raw = extraction(output_model, roles=[role_dict()])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    assert "gender" in profile.never_extract
    assert scrub(profile) is profile


def test_scrub_raises_on_a_forbidden_key(output_model, manifest, taxonomy):
    raw = extraction(output_model, roles=[role_dict()])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    profile.skills["nationality"] = SkillEntry()
    with pytest.raises(ProtectedFieldError, match="nationality"):
        scrub(profile)


def test_scrub_raises_on_a_nested_forbidden_key(output_model, manifest, taxonomy):
    raw = extraction(output_model, roles=[role_dict()])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    profile.derived["graduation_year"] = Envelope(value=2020, derivation="stated")
    with pytest.raises(ProtectedFieldError, match="graduation_year"):
        scrub(profile)


# --------------------------------------------------------------------------- #
# derived recompute
# --------------------------------------------------------------------------- #

def test_derived_cloud_and_sql_from_component_skills(output_model, manifest, taxonomy):
    raw = extraction(output_model, roles=[
        role_dict(skills_mentioned=["python", "aws_ecs", "postgresql", "github_actions"],
                  primary_skills=["python"]),
    ])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    assert profile.derived["cloud_platform_held"].value is True
    assert profile.derived["sql_held"].value is True
    assert profile.derived["ci_cd_held"].value is True
    assert profile.derived["iac_held"].value is None
    assert profile.derived["iac_held"].derivation == "absent"


def test_denied_skill_makes_derived_false_not_absent(output_model, manifest, taxonomy):
    raw = extraction(output_model,
                     roles=[role_dict(skills_mentioned=["python"])],
                     denied_skills=[{"skill": "aws", "quote": "not Kubernetes"}])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    assert profile.skills["aws"].held.value is False
    assert profile.skills["aws"].held.derivation == "denied"
    assert profile.derived["cloud_platform_held"].value is False
    assert profile.derived["cloud_platform_held"].derivation == "denied"


# --------------------------------------------------------------------------- #
# whole-profile assembly
# --------------------------------------------------------------------------- #

def test_build_profile_aggregates_and_scopes(output_model, manifest, taxonomy):
    raw = extraction(
        output_model,
        roles=[
            role_dict(start_raw="2022", end_raw="2026",
                      skills_mentioned=["python", "aws_ecs"], primary_skills=["python"]),
            role_dict(title_raw="Data Entry Specialist", title_canonical="non_software",
                      employer="RetailPlus", start_raw="2020", end_raw="2022",
                      is_backend_role=False, skills_mentioned=[], primary_skills=[],
                      quote="Backend Developer, FinServ Digital (2022-2026)"),
        ],
        skills_block=[{"skill": "docker", "quote": "Docker"}],
        projects=[{"title": "reporting API", "topics": ["backend"], "skills": ["python"],
                   "deployed": "yes", "quote": "Built Python services"}],
        unmatched_skills=["Golang", "Woodforce"],
    )
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())

    assert profile.experience.total_months.value == 72
    assert profile.experience.software_months.value == 48
    assert profile.experience.backend_months.value == 48
    assert profile.experience.num_roles.value == 2
    assert profile.experience.software_months.confidence == "medium"  # year precision

    # a skills-block-only skill is held but not dated
    assert profile.skills["docker"].held.value is True
    assert profile.skills["docker"].dated is False
    assert profile.skills["docker"].months.value is None
    assert profile.skills["docker"].months.derivation == "absent"

    # a role skill is dated and gets a union month count
    assert profile.skills["python"].dated is True
    assert profile.skills["python"].months.value == 48
    assert profile.skills["python"].last_used_year.value == 2026
    assert profile.skills["python"].proficiency.value == 3  # primary in a >=24-month role
    assert profile.skills["python"].project_count.value == 1

    # free text the model could not map is canonicalised, the rest is kept as-is
    assert "go" in profile.skills
    assert profile.unmatched_skills == ["Woodforce"]

    assert profile.project_counts_by_topic == {"backend": 1}
    assert profile.resolve("project_counts_by_topic.microservices").value == 0


def test_proficiency_ladder(output_model, manifest, taxonomy):
    raw = extraction(
        output_model,
        roles=[role_dict(start_raw="2025-01", end_raw="2025-07",
                         skills_mentioned=["python", "redis"], primary_skills=["python"])],
        skills_block=[{"skill": "docker", "quote": "Docker"}],
    )
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    assert profile.skills["python"].proficiency.value == 2   # primary, short role
    assert profile.skills["redis"].proficiency.value == 1    # mentioned only
    assert profile.skills["docker"].proficiency.value == 1
    assert profile.skills["docker"].proficiency.confidence == "low"


def test_seniority_from_titles_then_duration():
    from recourse_screen.schemas import Role

    senior = [Role(title_raw="Senior Backend Engineer", title_canonical="backend_engineer")]
    assert infer_seniority(senior, 72) == "senior"

    lead = [Role(title_raw="Tech Lead", title_canonical="backend_engineer")]
    assert infer_seniority(lead, 24) == "lead"

    junior = [Role(title_raw="Junior Backend Developer", title_canonical="backend_engineer")]
    assert infer_seniority(junior, 30) == "junior"

    plain = [Role(title_raw="Software Engineer", title_canonical="backend_engineer")]
    assert infer_seniority(plain, 48) == "mid"

    none_software = [Role(title_raw="Data Entry", title_canonical="non_software")]
    assert infer_seniority(none_software, 0) is None


# --------------------------------------------------------------------------- #
# sentinel mapping (the schema has no nullable fields; absence arrives as "" / "unclear")
# --------------------------------------------------------------------------- #

def test_sentinels_become_absent_envelopes(output_model, manifest, taxonomy):
    raw = extraction(output_model, roles=[role_dict(employer="")],
                     languages=[{"lang": "fi", "cefr": ""}])
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    assert profile.experience.roles[0].employer is None
    assert profile.languages[0].cefr is None
    assert profile.education.highest_level.derivation == "absent"
    assert profile.education.highest_level.value is None
    assert profile.eligibility.requires_sponsorship.derivation == "absent"


def test_tristates_become_booleans(output_model, manifest, taxonomy):
    raw = extraction(
        output_model,
        roles=[role_dict()],
        projects=[
            {"title": "a", "topics": ["backend"], "skills": [], "deployed": "yes",
             "quote": "Built Python services"},
            {"title": "b", "topics": ["tutorial"], "skills": [], "deployed": "no",
             "quote": "Backend Developer"},
            {"title": "c", "topics": ["other"], "skills": [], "deployed": "unclear",
             "quote": "Skills"},
        ],
        education={"highest_level": "bsc", "field": "computer science",
                   "in_progress": "no", "quote": "Backend Developer"},
        eligibility={"work_authorization_region": "EU", "requires_sponsorship": "no",
                     "location_country": "FI", "relocation_willing": "unclear",
                     "quote": "Backend Developer"},
    )
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    assert [p.deployed for p in profile.projects] == [True, False, None]
    assert profile.education.highest_level.value == "bsc"
    assert profile.education.in_progress.value is False
    assert profile.eligibility.requires_sponsorship.value is False
    assert profile.eligibility.relocation_willing.derivation == "absent"
    assert profile.project_counts_by_topic == {"backend": 1, "other": 1, "tutorial": 1}


def test_non_software_role_grants_held_but_no_professional_months(output_model, manifest, taxonomy):
    """A data-entry job whose bullet says "self-taught Python outside of work" must not
    turn into three years of professional Python."""
    raw = extraction(
        output_model,
        roles=[role_dict(title_raw="Data Entry / Support Specialist",
                         title_canonical="non_software", employer="RetailPlus",
                         start_raw="2023", end_raw="2026", is_backend_role=False,
                         skills_mentioned=["python"], primary_skills=["python"])],
        skills_block=[{"skill": "python", "quote": "Python"}],
    )
    profile = build_profile(raw, CV, as_of=AS_OF, manifest=manifest,
                            taxonomy=taxonomy, provenance=make_provenance())
    assert profile.skills["python"].held.value is True       # still held
    assert profile.skills["python"].months.value is None     # but not professional months
    assert profile.skills["python"].months.derivation == "absent"
    assert profile.skills["python"].dated is False
    assert profile.skills["python"].proficiency.value == 1
    assert profile.experience.software_months.value == 0
    assert profile.experience.total_months.value == 36
