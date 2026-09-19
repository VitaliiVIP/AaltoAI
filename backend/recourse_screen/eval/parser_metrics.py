"""Parser accuracy against the synthetic ground truth.

Implements rows 11 (parser extraction accuracy) and 12 (hallucination rate) of the
evaluation table in research/notes/ranking_mode_gaming_and_evaluation_brief.md.

The headline number is the split in row `skills.stated` vs `skills.omitted`: recall
on skills the renderer actually wrote down, versus recall on the ~30% of skills the
truth contains but the CV deliberately never mentions. The second number is the
honest ceiling of any parser, it will be near zero, and that is the finding that
motivates the restatement channel - not a bug to tune away.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Iterable

from ..schemas import Envelope, Evidence, Profile

_EXPERIENCE_FIELDS = ("total_months", "software_months", "backend_months")


def _held_skills(profile: Profile) -> set[str]:
    return {sid for sid, e in profile.skills.items()
            if e.held.value is True and e.held.derivation not in ("absent", "denied")}


def _skill_months(profile: Profile, sid: str) -> int | None:
    entry = profile.skills.get(sid)
    if entry is None:
        return None
    v = entry.months.value
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _num(env: Envelope) -> int | None:
    v = env.value
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _iter_evidence(profile: Profile) -> Iterable[Evidence]:
    def from_env(env: Envelope):
        yield from env.evidence

    for holder in (profile.experience.total_months, profile.experience.software_months,
                   profile.experience.backend_months, profile.experience.seniority,
                   profile.experience.num_roles, profile.education.highest_level,
                   profile.education.field, profile.education.in_progress,
                   profile.eligibility.work_authorization_region,
                   profile.eligibility.requires_sponsorship,
                   profile.eligibility.location_country,
                   profile.eligibility.relocation_willing):
        yield from from_env(holder)
    for entry in profile.skills.values():
        for env in (entry.held, entry.months, entry.last_used_year, entry.proficiency,
                    entry.project_count):
            yield from from_env(env)
    for env in profile.derived.values():
        yield from from_env(env)
    for r in profile.experience.roles:
        yield from r.evidence
    for p in profile.projects:
        yield from p.evidence
    for c in profile.certifications:
        yield from c.evidence


def _ratio(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def _f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if (p + r) else 0.0


def compare_profiles(extracted: Profile, truth: Profile, meta: dict) -> dict[str, Any]:
    """Compare one extracted profile against its ground truth."""
    t_held = _held_skills(truth)
    e_held = _held_skills(extracted)
    omitted = {s for s in (meta.get("omitted_skills") or []) if s in t_held}
    stated = t_held - omitted

    tp = len(e_held & t_held)
    fp = len(e_held - t_held)
    fn = len(t_held - e_held)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)

    hit_stated = len(e_held & stated)
    hit_omitted = len(e_held & omitted)

    # per-skill months MAE, over skills present in both with a numeric value
    errs: list[int] = []
    missing = 0
    for sid in sorted(t_held & e_held):
        tv, ev = _skill_months(truth, sid), _skill_months(extracted, sid)
        if tv is None:
            continue
        if ev is None:
            missing += 1
            continue
        errs.append(abs(ev - tv))

    exp_err: dict[str, int | None] = {}
    exp_vals: list[int] = []
    for f in _EXPERIENCE_FIELDS:
        tv = _num(getattr(truth.experience, f))
        ev = _num(getattr(extracted.experience, f))
        if tv is None or ev is None:
            exp_err[f] = None
        else:
            exp_err[f] = abs(ev - tv)
            exp_vals.append(exp_err[f])

    ev_list = [e for e in _iter_evidence(extracted)]
    n_ev = len(ev_list)
    n_ver = sum(1 for e in ev_list if e.verified is True)

    return {
        "source_file": meta.get("source_file") or truth.provenance.source_file,
        "archetype": meta.get("archetype"),
        "under_report": bool(meta.get("under_report")),
        "year_only_dates": bool(meta.get("year_only_dates")),
        "skills": {
            "n_truth": len(t_held), "n_extracted": len(e_held),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": _f1(precision, recall),
            "stated": {"n": len(stated), "hit": hit_stated, "recall": _ratio(hit_stated, len(stated))},
            "omitted": {"n": len(omitted), "hit": hit_omitted,
                        "recall": _ratio(hit_omitted, len(omitted))},
            "missed": sorted(t_held - e_held),
            "hallucinated": sorted(e_held - t_held),
        },
        "skill_months": {
            "n": len(errs), "n_missing": missing,
            "mae": _ratio(sum(errs), len(errs)) if errs else None,
            "max_abs_err": max(errs) if errs else None,
        },
        "experience_months": {
            **{f: exp_err[f] for f in _EXPERIENCE_FIELDS},
            "n": len(exp_vals),
            "mae": _ratio(sum(exp_vals), len(exp_vals)) if exp_vals else None,
        },
        "education_level": {
            "truth": truth.education.highest_level.value,
            "extracted": extracted.education.highest_level.value,
            "exact": extracted.education.highest_level.value == truth.education.highest_level.value,
        },
        "seniority": {
            "truth": truth.experience.seniority.value,
            "extracted": extracted.experience.seniority.value,
            "exact": extracted.experience.seniority.value == truth.experience.seniority.value,
        },
        "evidence": {"n": n_ev, "verified": n_ver, "rate": _ratio(n_ver, n_ev)},
        "hallucination": {
            "n_extracted": len(e_held), "n_hallucinated": len(e_held - t_held),
            "rate": _ratio(len(e_held - t_held), len(e_held)),
        },
        "roles": {
            "truth": len(truth.experience.roles), "extracted": len(extracted.experience.roles),
            "exact": len(extracted.experience.roles) == len(truth.experience.roles),
            "abs_err": abs(len(extracted.experience.roles) - len(truth.experience.roles)),
        },
    }


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Corpus-level summary: macro means plus micro (pooled) figures."""
    if not rows:
        return {"n": 0}

    tp = sum(r["skills"]["tp"] for r in rows)
    fp = sum(r["skills"]["fp"] for r in rows)
    fn = sum(r["skills"]["fn"] for r in rows)
    micro_p, micro_r = _ratio(tp, tp + fp), _ratio(tp, tp + fn)

    st_n = sum(r["skills"]["stated"]["n"] for r in rows)
    st_h = sum(r["skills"]["stated"]["hit"] for r in rows)
    om_n = sum(r["skills"]["omitted"]["n"] for r in rows)
    om_h = sum(r["skills"]["omitted"]["hit"] for r in rows)

    sm_n = sum(r["skill_months"]["n"] for r in rows)
    sm_sum = sum((r["skill_months"]["mae"] or 0) * r["skill_months"]["n"] for r in rows)
    ex_n = sum(r["experience_months"]["n"] for r in rows)
    ex_sum = sum((r["experience_months"]["mae"] or 0) * r["experience_months"]["n"] for r in rows)

    ev_n = sum(r["evidence"]["n"] for r in rows)
    ev_v = sum(r["evidence"]["verified"] for r in rows)
    h_n = sum(r["hallucination"]["n_extracted"] for r in rows)
    h_h = sum(r["hallucination"]["n_hallucinated"] for r in rows)

    per_field = {}
    for f in _EXPERIENCE_FIELDS:
        vals = [r["experience_months"][f] for r in rows if r["experience_months"][f] is not None]
        per_field[f] = {"mae": _mean([float(v) for v in vals]),
                        "median_abs_err": float(median(vals)) if vals else None, "n": len(vals)}

    under = [r for r in rows if r["under_report"]]
    yearly = [r for r in rows if r["year_only_dates"]]

    return {
        "n": len(rows),
        "skills": {
            "micro_precision": micro_p, "micro_recall": micro_r, "micro_f1": _f1(micro_p, micro_r),
            "macro_precision": _mean([r["skills"]["precision"] for r in rows]),
            "macro_recall": _mean([r["skills"]["recall"] for r in rows]),
            "macro_f1": _mean([r["skills"]["f1"] for r in rows]),
            "recall_stated": _ratio(st_h, st_n), "n_stated": st_n,
            "recall_omitted": _ratio(om_h, om_n), "n_omitted": om_n,
        },
        "skill_months": {"n": sm_n, "mae": _ratio(sm_sum, sm_n) if sm_n else None,
                         "n_missing": sum(r["skill_months"]["n_missing"] for r in rows)},
        "experience_months": {"n": ex_n, "mae": _ratio(ex_sum, ex_n) if ex_n else None,
                              "per_field": per_field},
        "education_level_exact": _mean([1.0 if r["education_level"]["exact"] else 0.0 for r in rows]),
        "seniority_exact": _mean([1.0 if r["seniority"]["exact"] else 0.0 for r in rows]),
        "evidence_verification_rate": _ratio(ev_v, ev_n),
        "evidence_n": ev_n,
        "hallucination_rate": _ratio(h_h, h_n),
        "role_count_exact": _mean([1.0 if r["roles"]["exact"] else 0.0 for r in rows]),
        "role_count_mae": _mean([float(r["roles"]["abs_err"]) for r in rows]),
        "subsets": {
            "under_report": {
                "n": len(under),
                "recall_stated": _ratio(sum(r["skills"]["stated"]["hit"] for r in under),
                                        sum(r["skills"]["stated"]["n"] for r in under)),
                "recall_omitted": _ratio(sum(r["skills"]["omitted"]["hit"] for r in under),
                                         sum(r["skills"]["omitted"]["n"] for r in under)),
            },
            "year_only_dates": {
                "n": len(yearly),
                "experience_mae": _mean([r["experience_months"]["mae"] for r in yearly
                                         if r["experience_months"]["mae"] is not None]),
            },
            "month_dates": {
                "n": len(rows) - len(yearly),
                "experience_mae": _mean([r["experience_months"]["mae"] for r in rows
                                         if not r["year_only_dates"]
                                         and r["experience_months"]["mae"] is not None]),
            },
        },
    }
