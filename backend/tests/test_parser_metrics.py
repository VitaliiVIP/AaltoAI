"""Metrics on a hand-built extracted-vs-truth pair, so the expected numbers can be
worked out by hand."""
from __future__ import annotations

import pytest

from recourse_screen.eval.parser_metrics import aggregate, compare_profiles
from recourse_screen.schemas import (
    Education,
    Eligibility,
    Envelope,
    Evidence,
    Experience,
    Profile,
    Provenance,
    Role,
    SkillEntry,
)

AS_OF = "2026-09-19"


def _prov(name: str = "synth_000.txt") -> Provenance:
    return Provenance(cv_sha256="x", source_file=name, extractor_model="m",
                      prompt_version="p", taxonomy_version="t", extracted_at=AS_OF)


def _skill(months: int | None, *, held: bool = True, evidence: list[Evidence] | None = None) -> SkillEntry:
    return SkillEntry(
        held=Envelope(value=held, derivation="stated" if held else "absent", confidence="high",
                      evidence=evidence or []),
        months=(Envelope(value=months, derivation="computed", confidence="medium")
                if months is not None else Envelope.absent()),
        dated=months is not None,
    )


def _profile(skills: dict[str, SkillEntry], *, roles: int = 2, total: int = 60,
             software: int = 60, backend: int = 36, level: str = "msc",
             seniority: str = "mid") -> Profile:
    rs = [Role(title_raw=f"Engineer {i}", title_canonical="data_scientist",
               start="2020-01", end="2021-01", months=12, is_backend_role=True)
          for i in range(roles)]
    return Profile(
        as_of=AS_OF, provenance=_prov(),
        experience=Experience(
            roles=rs,
            total_months=Envelope(value=total, derivation="computed"),
            software_months=Envelope(value=software, derivation="computed"),
            backend_months=Envelope(value=backend, derivation="computed"),
            seniority=Envelope(value=seniority, derivation="inferred"),
            num_roles=Envelope(value=roles, derivation="computed"),
        ),
        skills=skills,
        education=Education(highest_level=Envelope(value=level, derivation="stated")),
        eligibility=Eligibility(),
    )


# truth: 5 held skills, two of which the CV never mentioned.
TRUTH = _profile({
    "python": _skill(48),
    "docker": _skill(24),
    "sql": _skill(36),
    "kubernetes": _skill(18),   # omitted from the rendered CV
    "terraform": _skill(12),    # omitted from the rendered CV
})
META = {"source_file": "synth_000.txt", "archetype": "mid_backend", "under_report": True,
        "year_only_dates": False, "omitted_skills": ["kubernetes", "terraform"]}

# extracted: found 2 of 3 stated skills, 1 of 2 omitted ones, invented one.
EXTRACTED = _profile({
    "python": _skill(44),                 # 4 months off
    "docker": _skill(24),                 # exact
    "kubernetes": _skill(18),             # recovered despite being omitted
    "rust": _skill(6),                    # hallucinated
}, roles=2, total=60, software=54, backend=30)


@pytest.fixture(scope="module")
def row():
    return compare_profiles(EXTRACTED, TRUTH, META)


def test_skill_precision_recall_f1(row):
    sk = row["skills"]
    assert sk["n_truth"] == 5 and sk["n_extracted"] == 4
    assert (sk["tp"], sk["fp"], sk["fn"]) == (3, 1, 2)
    assert sk["precision"] == pytest.approx(3 / 4)
    assert sk["recall"] == pytest.approx(3 / 5)
    assert sk["f1"] == pytest.approx(2 * 0.75 * 0.6 / (0.75 + 0.6))
    assert sk["missed"] == ["sql", "terraform"]
    assert sk["hallucinated"] == ["rust"]


def test_stated_versus_omitted_recall_split(row):
    sk = row["skills"]
    assert sk["stated"]["n"] == 3 and sk["stated"]["hit"] == 2
    assert sk["stated"]["recall"] == pytest.approx(2 / 3)
    assert sk["omitted"]["n"] == 2 and sk["omitted"]["hit"] == 1
    assert sk["omitted"]["recall"] == pytest.approx(1 / 2)


def test_skill_months_mae_uses_only_skills_in_both(row):
    # python off by 4, docker exact, kubernetes exact -> mean 4/3
    assert row["skill_months"]["n"] == 3
    assert row["skill_months"]["mae"] == pytest.approx(4 / 3)
    assert row["skill_months"]["max_abs_err"] == 4


def test_experience_months_mae(row):
    e = row["experience_months"]
    assert (e["total_months"], e["software_months"], e["backend_months"]) == (0, 6, 6)
    assert e["mae"] == pytest.approx(4.0)


def test_categorical_exact_match_and_role_count(row):
    assert row["education_level"]["exact"] is True
    assert row["seniority"]["exact"] is True
    assert row["roles"]["exact"] is True and row["roles"]["abs_err"] == 0


def test_hallucination_rate(row):
    assert row["hallucination"]["rate"] == pytest.approx(1 / 4)


def test_missing_extracted_months_are_counted_not_averaged():
    ext = _profile({"python": _skill(None), "docker": _skill(24)})
    r = compare_profiles(ext, TRUTH, META)
    assert r["skill_months"]["n"] == 1 and r["skill_months"]["n_missing"] == 1
    assert r["skill_months"]["mae"] == pytest.approx(0.0)


def test_evidence_verification_rate():
    ext = _profile({
        "python": _skill(48, evidence=[Evidence(quote="Python", verified=True),
                                       Evidence(quote="py", verified=False)]),
        "docker": _skill(24, evidence=[Evidence(quote="Docker", verified=True)]),
    })
    r = compare_profiles(ext, TRUTH, META)
    assert r["evidence"] == {"n": 3, "verified": 2, "rate": pytest.approx(2 / 3)}


def test_mismatched_categoricals_are_flagged():
    ext = _profile({"python": _skill(48)}, roles=3, level="bsc", seniority="senior")
    r = compare_profiles(ext, TRUTH, META)
    assert r["education_level"]["exact"] is False
    assert r["seniority"]["exact"] is False
    assert r["roles"]["exact"] is False and r["roles"]["abs_err"] == 1


def test_aggregate_micro_f1_pools_counts(row):
    second = compare_profiles(_profile({"python": _skill(48), "sql": _skill(36)}), TRUTH, META)
    agg = aggregate([row, second])
    # row: tp 3 fp 1 fn 2; second: tp 2 fp 0 fn 3 -> micro P 5/6, micro R 5/10
    assert agg["n"] == 2
    assert agg["skills"]["micro_precision"] == pytest.approx(5 / 6)
    assert agg["skills"]["micro_recall"] == pytest.approx(0.5)
    assert agg["skills"]["micro_f1"] == pytest.approx(2 * (5 / 6) * 0.5 / ((5 / 6) + 0.5))
    # pooled stated/omitted recall: stated 2+2 of 3+3, omitted 1+0 of 2+2
    assert agg["skills"]["recall_stated"] == pytest.approx(4 / 6)
    assert agg["skills"]["recall_omitted"] == pytest.approx(1 / 4)
    assert agg["skills"]["macro_precision"] == pytest.approx((0.75 + 1.0) / 2)
    assert agg["subsets"]["under_report"]["n"] == 2


def test_aggregate_handles_empty():
    assert aggregate([]) == {"n": 0}
