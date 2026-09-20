"""The sampler is the ground truth, so it has to be exactly right and exactly
reproducible. Everything here is pure Python; no Claude call is made."""
from __future__ import annotations

import numpy as np
import pytest

from recourse_screen import config
from recourse_screen.dates import union_months, ym_to_index
from recourse_screen.loaders import load_manifest, load_taxonomy
from recourse_screen.synth.sampler import sample_corpus, sample_truth

TAX = load_taxonomy()
MAN = load_manifest("data_science.json")


def _one(seed: int, idx: int = 0):
    return sample_truth(np.random.default_rng(seed), taxonomy=TAX, manifest=MAN,
                        as_of=config.AS_OF, idx=idx)


def test_deterministic_for_a_seed():
    a, ma = _one(7)
    b, mb = _one(7)
    assert a.model_dump_json() == b.model_dump_json()
    assert ma == mb


def test_different_seeds_differ():
    a, _ = _one(1)
    b, _ = _one(2)
    assert a.model_dump_json() != b.model_dump_json()


def test_corpus_index_is_stable_regardless_of_n():
    small = sample_corpus(3, seed=11, taxonomy=TAX, manifest=MAN)
    big = sample_corpus(9, seed=11, taxonomy=TAX, manifest=MAN)
    for i in range(3):
        assert small[i][0].model_dump_json() == big[i][0].model_dump_json()
        assert small[i][1] == big[i][1]


def test_skill_months_equal_union_of_mentioning_roles():
    for profile, _ in sample_corpus(25, seed=3, taxonomy=TAX, manifest=MAN):
        for sid, entry in profile.skills.items():
            mentioning = [r for r in profile.experience.roles if sid in r.skills_mentioned]
            if not mentioning:
                # skills-list-only entries carry no months at all
                assert entry.dated is False
                assert entry.months.value is None
                continue
            assert entry.dated is True
            assert entry.months.value == union_months([(r.start, r.end) for r in mentioning])


def test_experience_months_are_unions_not_sums():
    for profile, meta in sample_corpus(25, seed=5, taxonomy=TAX, manifest=MAN):
        roles = profile.experience.roles
        assert profile.experience.total_months.value == union_months(
            [(r.start, r.end) for r in roles])
        assert profile.experience.software_months.value == union_months(
            [(r.start, r.end) for r in roles if r.title_canonical != "non_software"])
        assert profile.experience.backend_months.value == union_months(
            [(r.start, r.end) for r in roles if r.is_backend_role])
        assert profile.experience.software_months.value <= profile.experience.total_months.value
        assert profile.experience.backend_months.value <= profile.experience.software_months.value
        if meta["overlap"]:
            # an overlapping contract must make the union strictly cheaper than the sum
            assert profile.experience.total_months.value < sum(r.months for r in roles)


def test_roles_end_at_or_before_as_of():
    cutoff = ym_to_index(config.AS_OF[:7])
    for profile, _ in sample_corpus(25, seed=9, taxonomy=TAX, manifest=MAN):
        for r in profile.experience.roles:
            assert ym_to_index(r.start) < ym_to_index(r.end) <= cutoff


def test_omitted_skills_stay_in_the_truth_and_leave_the_render():
    from recourse_screen.synth.render import build_view

    seen = 0
    for profile, meta in sample_corpus(40, seed=2, taxonomy=TAX, manifest=MAN):
        if not meta["under_report"]:
            continue
        seen += 1
        view = build_view(profile, meta, taxonomy=TAX)
        shown = set(view["skills_section_labels"])
        for r in view["roles_reverse_chronological"]:
            shown |= set(r["skills_used"]) | set(r["emphasise"])
        for sid in meta["omitted_skills"]:
            assert profile.skills[sid].held.value is True, "omitted skills stay in the truth"
            assert profile.skills[sid].months.value is not None
            assert TAX.label(sid) not in shown, "omitted skills must not reach the rendered CV"
    assert seen >= 5, "expected roughly 30% under-reporting variants in 40 samples"


def test_year_only_dates_snap_to_mid_year():
    seen = 0
    for profile, meta in sample_corpus(60, seed=4, taxonomy=TAX, manifest=MAN):
        if not meta["year_only_dates"]:
            continue
        seen += 1
        for r in profile.experience.roles:
            assert r.date_precision == "year"
            assert r.start.endswith("-07"), r.start
            assert r.end.endswith("-07") or r.end == config.AS_OF[:7], r.end
    assert seen >= 5, "expected roughly 20% year-only variants in 60 samples"


def test_month_precision_profiles_are_not_snapped():
    months = set()
    for profile, meta in sample_corpus(40, seed=6, taxonomy=TAX, manifest=MAN):
        if meta["year_only_dates"]:
            continue
        months |= {r.start[-2:] for r in profile.experience.roles}
    assert len(months) > 3


def test_proficiency_heuristic_matches_the_documented_rule():
    for profile, _ in sample_corpus(25, seed=8, taxonomy=TAX, manifest=MAN):
        roles = profile.experience.roles
        for sid, entry in profile.skills.items():
            prim = [r for r in roles if sid in r.primary_skills]
            months = entry.months.value
            if any((r.months or 0) >= 24 for r in prim):
                expected = 3
            elif prim or (months is not None and months >= 12):
                expected = 2
            else:
                expected = 1
            assert entry.proficiency.value == expected, sid


def test_cooccurrence_prior_pulls_in_implied_skills():
    """kubernetes without docker anywhere in the corpus would mean the prior is dead."""
    pairs = 0
    for profile, _ in sample_corpus(40, seed=12, taxonomy=TAX, manifest=MAN):
        for r in profile.experience.roles:
            if "kubernetes" in r.skills_mentioned and "docker" in r.skills_mentioned:
                pairs += 1
    assert pairs > 0


def test_derived_booleans_are_recomputed():
    for profile, _ in sample_corpus(20, seed=13, taxonomy=TAX, manifest=MAN):
        assert set(profile.derived) == set(MAN.derived)
        for name, rule in MAN.derived.items():
            truthy = any(profile.resolve(p).value is True for p in rule.any_of)
            assert profile.derived[name].value is (True if truthy else None)


def test_provenance_marks_the_profile_as_synthetic():
    profile, meta = _one(21, idx=7)
    assert profile.provenance.cv_sha256 == "synthetic"
    assert profile.provenance.extractor_model == "truth"
    assert profile.provenance.source_file == "synth_007.txt"
    assert meta["source_file"] == "synth_007.txt"


def test_archetype_mix_favours_backend():
    metas = [m for _, m in sample_corpus(120, seed=17, taxonomy=TAX, manifest=MAN)]
    backend = sum(1 for m in metas if m["archetype"].endswith("_backend"))
    assert backend / len(metas) > 0.35


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_profiles_validate_and_carry_no_protected_fields(seed):
    profile, _ = _one(seed)
    dumped = profile.model_dump()
    assert "name" not in dumped and "date_of_birth" not in dumped
    assert profile.experience.num_roles.value == len(profile.experience.roles)


# --------------------------------------------------------------------------- #
# render-side helpers (no Claude call)
# --------------------------------------------------------------------------- #

def test_strip_markdown_leaves_plain_cv_text():
    from recourse_screen.synth.render import strip_markdown

    out = strip_markdown("# Jane Doe\n\n## Experience\n\n**Backend Developer** - Acme\n"
                         "* built things\n+ shipped things\n\n\n\nEnd\n")
    assert "#" not in out and "**" not in out
    assert out.startswith("Jane Doe")
    assert "- built things" in out and "- shipped things" in out
    assert "\n\n\n" not in out


def test_reconcile_meta_moves_leaked_skills_back_to_stated():
    from recourse_screen.synth.render import reconcile_meta

    meta = {"omitted_skills": ["ci_cd", "kubernetes"], "under_report": True}
    text = "Owned the deployment pipeline for two services and wrote Terraform modules."
    out = reconcile_meta(dict(meta), text, taxonomy=TAX)
    # "deployment pipeline" is an alias of ci_cd, so that skill was not really omitted
    assert out["leaked_skills"] == ["ci_cd"]
    assert out["omitted_skills"] == ["kubernetes"]
    assert out["under_report"] is True


def test_reconcile_meta_clears_under_report_when_nothing_is_omitted():
    from recourse_screen.synth.render import reconcile_meta

    out = reconcile_meta({"omitted_skills": ["docker"], "under_report": True},
                         "Containerised the service with Docker.", taxonomy=TAX)
    assert out["omitted_skills"] == [] and out["under_report"] is False


def test_reconcile_meta_flags_duration_statements():
    from recourse_screen.synth.render import reconcile_meta

    out = reconcile_meta({"omitted_skills": []}, "Backend engineer with 5 years of Python.",
                         taxonomy=TAX)
    assert out["duration_phrases"] == ["5 years"]
    clean = reconcile_meta({"omitted_skills": []}, "Backend engineer. Mar 2022 - Present.",
                           taxonomy=TAX)
    assert clean["duration_phrases"] == []


def test_render_view_never_exposes_a_derived_value():
    from recourse_screen.synth.render import build_view

    for profile, meta in sample_corpus(20, seed=14, taxonomy=TAX, manifest=MAN):
        blob = repr(build_view(profile, meta, taxonomy=TAX))
        for forbidden in ("months", "seniority", "proficiency", "total_months",
                          "project_count", "derived"):
            assert forbidden not in blob, forbidden
