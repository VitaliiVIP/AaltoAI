"""The parse, as a human can check it.

`/candidates/{id}/cv` hands the UI the CV text and this list side by side, so a
recruiter (or the candidate, or an auditor) can see every attribute the screen
reads and the exact words it was read from. The offsets come straight from
`extract.postprocess.verify_evidence`, which already located every quote in the
CV text, so nothing here re-searches the document.

Three rules the shape follows:

- An attribute with no evidence is still an attribute. "computed from the roles
  above" and "the CV did not say" are the two most important things this view
  can show, and dropping those rows would make the parse look tidier than it is.
- Protected features are never listed. They are unrepresentable in a Profile, and
  the manifest paths that name them (`education.graduation_year`) are skipped
  explicitly rather than by accident.
- Skills collapse to one row each. Five envelopes per skill is the storage shape,
  not a reading order; the secondary fields ride along as `detail`.
"""
from __future__ import annotations

from typing import Any

from ..loaders import load_taxonomy
from ..schemas import Envelope, Evidence, JobTemplate, Manifest, Profile

__all__ = ["attributes_for"]

# Group headings, in the order a CV is usually read.
EXPERIENCE, SKILLS, PROJECTS, EDUCATION, ELIGIBILITY, DERIVED, CERTS = (
    "Experience", "Skills", "Projects", "Education", "Eligibility",
    "Derived signals", "Certifications",
)

_EXPERIENCE_FIELDS = {
    "total_months": "total professional experience",
    "software_months": "professional software experience",
    "backend_months": "professional backend experience",
    "data_months": "professional data science experience",
    "seniority": "seniority",
    "num_roles": "number of roles",
}
_EDUCATION_FIELDS = {
    "highest_level": "highest completed degree",
    "field": "field of study",
    "in_progress": "degree in progress",
}
_ELIGIBILITY_FIELDS = {
    "work_authorization_region": "work authorisation region",
    "requires_sponsorship": "needs visa sponsorship",
    "location_country": "country of residence",
    "relocation_willing": "willing to relocate",
}


def _scored_paths(job: JobTemplate | None) -> set[str]:
    """Paths the job actually decides on: scored terms plus hard requirements."""
    if job is None:
        return set()
    return set(job.score) | {ko.path for ko in job.parsed_knockouts}


def _phrase(path: str, manifest: Manifest | None, fallback: str) -> str:
    """The employer-facing phrase when the manifest has one, else our own."""
    spec = manifest.features.get(path) if manifest else None
    if spec is None or spec.actionability == "protected_never_use":
        return fallback
    return spec.candidate_phrase


def _evidence(*sources: list[Evidence]) -> list[dict]:
    """Union of several evidence lists, de-duplicated, in CV order.

    A skill is usually evidenced by the same two lines over and over (the role
    header and the skills list); showing them once is the whole point of merging.
    """
    seen: dict[tuple[str, int | None, int | None], Evidence] = {}
    for source in sources:
        for ev in source:
            seen.setdefault((ev.quote, ev.start, ev.end), ev)
    ordered = sorted(seen.values(), key=lambda e: (e.start is None, e.start or 0))
    return [e.model_dump(mode="json") for e in ordered]


def _row(
    *,
    path: str,
    label: str,
    group: str,
    value: Any,
    derivation: str,
    confidence: str,
    evidence: list[dict],
    detail: str | None = None,
    unit: str | None = None,
    scored: bool = False,
) -> dict:
    return {
        "path": path, "label": label, "group": group, "value": value,
        # `unit` is only ever "months": it is the one value the UI cannot format
        # from the number alone, and inventing a unit for booleans reads worse
        # than leaving them bare.
        "detail": detail, "unit": unit, "derivation": derivation,
        "confidence": confidence, "scored": scored, "evidence": evidence,
    }


def _envelope_row(
    path: str, label: str, group: str, env: Envelope, scored: set[str],
) -> dict:
    return _row(
        path=path, label=label, group=group, value=env.value,
        unit="months" if path.endswith("_months") else None,
        derivation=env.derivation, confidence=env.confidence,
        evidence=_evidence(env.evidence), scored=path in scored,
    )


def _role_rows(profile: Profile) -> list[dict]:
    rows = []
    for i, role in enumerate(profile.experience.roles):
        bits = []
        if role.start and role.end:
            bits.append(f"{role.start} → {role.end}")
        bits.append(role.title_canonical.replace("_", " "))
        if role.date_precision != "month":
            bits.append(f"dates to the {role.date_precision}")
        label = role.title_raw
        if role.employer:
            label = f"{role.title_raw} — {role.employer}"
        rows.append(_row(
            path=f"experience.roles[{i}]", label=label, group=EXPERIENCE,
            # A role is not an Envelope: its "value" is the span it contributes.
            value=role.months, unit="months", detail=" · ".join(bits),
            derivation="stated", confidence="high",
            evidence=_evidence(role.evidence),
        ))
    return rows


def _skill_rows(profile: Profile, manifest: Manifest | None, scored: set[str]) -> list[dict]:
    tax = load_taxonomy()
    rows = []
    for skill_id, entry in sorted(profile.skills.items()):
        detail = []
        if not entry.dated:
            detail.append("named in a skills list — no dates to count")
        elif entry.months.is_known:
            detail.append(f"{entry.months.value} mo")
        if entry.last_used_year.is_known:
            detail.append(f"last used {entry.last_used_year.value}")
        if entry.proficiency.is_known:
            detail.append(f"proficiency {entry.proficiency.value}/3")
        if entry.project_count.is_known and entry.project_count.value:
            detail.append(f"{entry.project_count.value} project(s)")
        paths = {f"skills.{skill_id}.{f}" for f in
                 ("held", "months", "last_used_year", "proficiency", "project_count")}
        rows.append(_row(
            path=f"skills.{skill_id}.held",
            label=_phrase(f"skills.{skill_id}.held", manifest, tax.label(skill_id)),
            group=SKILLS, value=entry.held.value, detail=" · ".join(detail) or None,
            derivation=entry.held.derivation, confidence=entry.held.confidence,
            evidence=_evidence(entry.held.evidence, entry.months.evidence,
                               entry.last_used_year.evidence, entry.proficiency.evidence,
                               entry.project_count.evidence),
            scored=bool(paths & scored),
        ))
    return rows


def _project_rows(profile: Profile, manifest: Manifest | None, scored: set[str]) -> list[dict]:
    rows = []
    for i, project in enumerate(profile.projects):
        detail = [t.replace("_", " ") for t in project.topics]
        if project.deployed:
            detail.append("deployed")
        rows.append(_row(
            path=f"projects[{i}]", label=project.title, group=PROJECTS,
            value=None, detail=" · ".join(detail) or None,
            derivation="stated", confidence="medium",
            evidence=_evidence(project.evidence),
        ))
    # The counts are what the scorer actually reads, so they are shown as their
    # own rows even though they are just a tally of the projects above.
    for topic, count in sorted(profile.project_counts_by_topic.items()):
        path = f"project_counts_by_topic.{topic}"
        rows.append(_row(
            path=path,
            label=_phrase(path, manifest, f"{topic.replace('_', ' ')} projects"),
            group=PROJECTS, value=count, detail="counted from the projects above",
            derivation="computed", confidence="medium", evidence=[],
            scored=path in scored,
        ))
    return rows


def attributes_for(
    profile: Profile, manifest: Manifest | None = None, job: JobTemplate | None = None,
) -> list[dict]:
    """Every attribute the screen read out of this CV, in reading order."""
    scored = _scored_paths(job)
    rows: list[dict] = _role_rows(profile)

    for field, fallback in _EXPERIENCE_FIELDS.items():
        path = f"experience.{field}"
        rows.append(_envelope_row(
            path, _phrase(path, manifest, fallback), EXPERIENCE,
            getattr(profile.experience, field), scored,
        ))

    rows += _skill_rows(profile, manifest, scored)
    rows += _project_rows(profile, manifest, scored)

    for field, fallback in _EDUCATION_FIELDS.items():
        path = f"education.{field}"
        rows.append(_envelope_row(
            path, _phrase(path, manifest, fallback), EDUCATION,
            getattr(profile.education, field), scored,
        ))

    for field, fallback in _ELIGIBILITY_FIELDS.items():
        path = f"eligibility.{field}"
        rows.append(_envelope_row(
            path, _phrase(path, manifest, fallback), ELIGIBILITY,
            getattr(profile.eligibility, field), scored,
        ))

    for name, env in sorted(profile.derived.items()):
        path = f"derived.{name}"
        rows.append(_envelope_row(
            path, _phrase(path, manifest, name.replace("_", " ")), DERIVED, env, scored,
        ))

    for cert in profile.certifications:
        rows.append(_row(
            path=f"certifications.{cert.cert_id}", label=cert.cert_id.replace("_", " "),
            group=CERTS, value=True, detail=cert.issuer, derivation="stated",
            confidence="high", evidence=_evidence(cert.evidence),
            scored=f"certifications.{cert.cert_id}" in scored,
        ))

    return rows
