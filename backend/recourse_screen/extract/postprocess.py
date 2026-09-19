"""Deterministic post-processing: LLM output -> `Profile`.

Everything the model is not allowed to compute happens here, in this order:

1. date normalisation and per-role month arithmetic (against `as_of`, never the clock)
2. role-evidence verification - a role whose only quote is not in the CV loses its dates,
   because role dates feed every downstream number including a knockout
3. taxonomy canonicalisation of `unmatched_skills`
4. per-skill months as a UNION of role intervals, recency, proficiency, project counts
5. experience aggregates (total / software / backend months, seniority, num_roles)
6. project counts by topic
7. evidence verification for every remaining quote, with the confidence and
   knockout-drop policy from the design brief
8. the protected-attribute scrub
9. `derived.*` recomputation from the manifest rules

The small pieces (`normalise_roles`, `skill_months`, `verify_evidence`, `scrub`) are pure
functions so they can be unit-tested without touching the API.
"""
from __future__ import annotations

import enum
import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Iterator

from pydantic import BaseModel

from ..dates import clamp_end, interval_months, normalise_date, union_months
from ..derived import recompute_derived
from ..loaders import Taxonomy
from ..schemas import (
    NEVER_EXTRACT,
    Certification,
    Confidence,
    Education,
    Eligibility,
    Envelope,
    Evidence,
    Experience,
    Language,
    Manifest,
    Profile,
    Project,
    Provenance,
    Role,
    SkillEntry,
)

__all__ = [
    "ProtectedFieldError",
    "QuoteIndex",
    "build_profile",
    "infer_seniority",
    "normalise_roles",
    "pii_warnings",
    "professional_roles",
    "scrub",
    "skill_months",
    "verification_stats",
    "verify_evidence",
]


class ProtectedFieldError(RuntimeError):
    """A protected attribute key reached the profile. Always a bug, never recoverable."""


# Profile paths that a knockout rule can read. An unverified sole quote on one of these
# drops the value to absent rather than merely lowering confidence, because a fabricated
# knockout value silently decides the case. Role dates are handled separately, in
# `verify_role_evidence`, since they feed `experience.software_months`.
KNOCKOUT_PATHS: frozenset[str] = frozenset({"skills.python.held"})

_SENIOR_WORDS = ("senior", "sr.", "sr ")
_LEAD_WORDS = ("lead", "principal", "head of", "staff engineer", "architect")
_JUNIOR_WORDS = ("junior", "jr.", "intern", "trainee", "graduate", "apprentice")

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# A year range like "(2022-2026)" trips a naive phone pattern, so a candidate match
# must also carry at least 9 digits - shorter than any real international number.
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_MIN_PHONE_DIGITS = 9


# --------------------------------------------------------------------------- #
# 1. Dates
# --------------------------------------------------------------------------- #

def _opt(value: Any) -> str | None:
    """LLM sentinel -> None. The extraction schema has no nullable fields (they blow the
    decoding grammar budget), so absence arrives as an empty string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tri(value: Any) -> bool | None:
    """LLM tri-state ('yes' / 'no' / 'unclear') -> True / False / None."""
    if isinstance(value, bool) or value is None:
        return value
    return {"yes": True, "no": False}.get(str(value).strip().lower())


def _sid(value: Any) -> str:
    """Taxonomy id as a plain string. The LLM-facing schema uses an Enum (a shared
    `$defs` entry keeps the decoding grammar small), and Enum members do not hash like
    their string values, so ids are flattened at this boundary."""
    return value.value if isinstance(value, enum.Enum) else str(value)


def normalise_roles(raw_roles: Iterable[Any], *, as_of: str) -> list[Role]:
    """Turn the LLM's raw role records into `Role`s with normalised dates and months.

    A role with no parsable start, or with a start but no parsable end, keeps
    `months = None`: an unknown duration is not a zero duration and not an open-ended
    one. "present" resolves to `as_of`; an end after `as_of` is clamped to `as_of`.
    Precision is the weaker of the two endpoints and is carried on the role so the
    explainer can put an error bar on a year-only CV.
    """
    roles: list[Role] = []
    for raw in raw_roles:
        start, start_prec = normalise_date(_opt(raw.start_raw), as_of)
        end, end_prec = normalise_date(_opt(raw.end_raw), as_of)

        months: int | None = None
        precision = "unknown"
        if start is None:
            end = None
        elif end is None:
            precision = start_prec
        else:
            end = clamp_end(end, as_of)
            months = interval_months(start, end)
            precision = "year" if "year" in (start_prec, end_prec) else start_prec

        roles.append(
            Role(
                title_raw=raw.title_raw,
                title_canonical=raw.title_canonical,
                employer=_opt(raw.employer),
                start=start,
                end=end,
                date_precision=precision,  # type: ignore[arg-type]
                months=months,
                is_backend_role=bool(raw.is_backend_role),
                skills_mentioned=list(dict.fromkeys(_sid(s) for s in raw.skills_mentioned)),
                primary_skills=list(dict.fromkeys(_sid(s) for s in raw.primary_skills)),
                evidence=[Evidence(quote=raw.quote, section="experience")],
            )
        )
    return roles


def _intervals(roles: Iterable[Role]) -> list[tuple[str, str]]:
    return [(r.start, r.end) for r in roles if r.start and r.end]


def _precision_confidence(roles: Iterable[Role]) -> Confidence:
    precisions = {r.date_precision for r in roles}
    if not precisions or "unknown" in precisions:
        return "low"
    return "medium" if "year" in precisions else "high"


# --------------------------------------------------------------------------- #
# 2. Quote verification
# --------------------------------------------------------------------------- #

_DASHES = "‐‑‒–—―−"
_QUOTE_CHARS = {"‘": "'", "’": "'", "“": '"', "”": '"'}


def _norm_char(ch: str) -> str:
    if ch in _DASHES:
        return "-"
    if ch in _QUOTE_CHARS:
        return _QUOTE_CHARS[ch]
    low = ch.lower()
    return low if len(low) == 1 else ch


def _normalise(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs, unify dashes/quotes, lowercase; keep an index map back
    into the original string so a fallback hit still yields real character offsets."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(_norm_char(ch))
            idx.append(i)
            prev_space = False
    return "".join(out), idx


class QuoteIndex:
    """Substring search over the CV text, with a whitespace-tolerant second chance.

    `pdftotext -layout` fills two-column role headers with long runs of spaces, and a
    model transcribing "Embedded Software Engineer      Aug 2025-Present" rarely gets the
    run length right. An exact hit is tried first; the fallback matches on collapsed
    whitespace, unified dashes and lowercase, and still returns offsets into the
    original text.
    """

    def __init__(self, cv_text: str) -> None:
        self.text = cv_text
        self._norm, self._map = _normalise(cv_text)

    def find(self, quote: str) -> tuple[int, int] | None:
        if not quote:
            return None
        idx = self.text.find(quote)
        if idx != -1:
            return idx, idx + len(quote)
        needle, _ = _normalise(quote)
        needle = needle.strip()
        if not needle:
            return None
        j = self._norm.find(needle)
        if j == -1:
            return None
        return self._map[j], self._map[j + len(needle) - 1] + 1


def _locate(evidence: list[Evidence], index: QuoteIndex) -> bool:
    """Set verified/start/end on each Evidence. Returns True if any of them verified."""
    any_ok = False
    for ev in evidence:
        span = index.find(ev.quote)
        ev.verified = span is not None
        if span is not None:
            ev.start, ev.end = span
            any_ok = True
        else:
            ev.start = ev.end = None
    return any_ok


def verify_role_evidence(roles: list[Role], index: QuoteIndex) -> list[Role]:
    """Verify role header quotes and drop the dates of any role that cannot be located.

    Role dates are knockout-relevant (they drive `experience.software_months`), so an
    unverifiable role keeps its title but contributes no months to anything.
    """
    for role in roles:
        if role.evidence and not _locate(role.evidence, index):
            role.start = role.end = None
            role.months = None
            role.date_precision = "unknown"
    return roles


def verify_evidence(profile: Profile, cv_text: str) -> Profile:
    """Verify every quote in the profile and apply the downgrade policy.

    - quote found (exactly, or after whitespace normalisation) -> `verified`, offsets set
    - every quote on an envelope fails -> `confidence` drops to "low"
    - ... and if the path is knockout-relevant, the value drops to absent

    Idempotent, so it is safe to call after role evidence was already verified.
    """
    index = QuoteIndex(cv_text)
    for path, envelope, evidence in _iter_evidence(profile):
        if not evidence:
            continue
        any_ok = _locate(evidence, index)
        if any_ok or envelope is None:
            continue
        envelope.confidence = "low"
        if path in KNOCKOUT_PATHS:
            envelope.value = None
            envelope.derivation = "absent"
    return profile


def _iter_evidence(profile: Profile) -> Iterator[tuple[str, Envelope | None, list[Evidence]]]:
    """(path, owning envelope or None, evidence list) for every quote in the profile."""
    for i, role in enumerate(profile.experience.roles):
        yield f"experience.roles[{i}]", None, role.evidence
    for field in ("total_months", "software_months", "backend_months", "seniority", "num_roles"):
        env = getattr(profile.experience, field)
        yield f"experience.{field}", env, env.evidence
    for skill_id, entry in profile.skills.items():
        for field in ("held", "months", "last_used_year", "proficiency", "project_count"):
            env = getattr(entry, field)
            yield f"skills.{skill_id}.{field}", env, env.evidence
    for i, project in enumerate(profile.projects):
        yield f"projects[{i}]", None, project.evidence
    for field in ("highest_level", "field", "in_progress"):
        env = getattr(profile.education, field)
        yield f"education.{field}", env, env.evidence
    for i, cert in enumerate(profile.certifications):
        yield f"certifications[{i}]", None, cert.evidence
    for field in ("work_authorization_region", "requires_sponsorship", "location_country",
                  "relocation_willing"):
        env = getattr(profile.eligibility, field)
        yield f"eligibility.{field}", env, env.evidence


def verification_stats(profile: Profile) -> dict[str, Any]:
    """Side-channel quality metric: how many quotes were found in the CV."""
    total = verified = 0
    failures: list[str] = []
    for path, _env, evidence in _iter_evidence(profile):
        for ev in evidence:
            total += 1
            if ev.verified:
                verified += 1
            else:
                failures.append(f"{path}: {ev.quote[:70]!r}")
    return {
        "total": total,
        "verified": verified,
        "rate": (verified / total) if total else 1.0,
        "failures": failures,
    }


# --------------------------------------------------------------------------- #
# 3-4. Skills
# --------------------------------------------------------------------------- #

def skill_months(roles: Iterable[Role], skill_id: str) -> int | None:
    """Months of a skill = size of the UNION of the intervals of the roles that mention it.

    Summing would double-count concurrent contracts, which are common on real CVs.
    Returns None when no role that mentions the skill has usable dates.
    """
    dated = [r for r in roles if skill_id in r.skills_mentioned and r.start and r.end]
    if not dated:
        return None
    return union_months(_intervals(dated))


def professional_roles(roles: Iterable[Role]) -> list[Role]:
    """The roles that count as professional experience with a technology.

    A `non_software` role is excluded even when it mentions a skill. Otherwise a CV whose
    only job is "Data Entry / Support Specialist (2023-2026)" with the bullet "Self-taught
    Python basics outside of work" earns three years of professional Python, which is the
    opposite of what the page says. Such a mention still makes the skill *held*; it just
    contributes no months, no recency and no proficiency.
    """
    return [r for r in roles if r.title_canonical != "non_software"]


def _proficiency(skill_id: str, roles: list[Role], months: int | None) -> tuple[int, Confidence]:
    """Inferred 0-3 depth score. Documented heuristic, deliberately crude:

      3  primary skill (in the role title or its first two bullets) of a role of >= 24 months
      2  primary skill of any role, or mentioned in roles totalling >= 12 months
      1  mentioned in a role of unknown/short duration, or listed only in a skills block

    `roles` should already be filtered to `professional_roles`.
    """
    mentioning = [r for r in roles if skill_id in r.skills_mentioned]
    primary = [r for r in roles if skill_id in r.primary_skills]
    if any((r.months or 0) >= 24 for r in primary):
        return 3, "medium"
    if primary or (months is not None and months >= 12):
        return 2, "medium"
    if mentioning:
        return 1, "medium"
    return 1, "low"


def _canonicalise_unmatched(
    raw_unmatched: Iterable[str], taxonomy: Taxonomy
) -> tuple[dict[str, str], list[str]]:
    """Second chance for free-text skills: (recovered id -> raw string, still unmatched)."""
    recovered: dict[str, str] = {}
    leftover: list[str] = []
    for raw in raw_unmatched:
        cid = taxonomy.canonicalise(raw)
        if cid is not None:
            recovered.setdefault(cid, raw)
        elif raw not in leftover:
            leftover.append(raw)
    return recovered, leftover


# --------------------------------------------------------------------------- #
# 5. Experience aggregates
# --------------------------------------------------------------------------- #

def infer_seniority(roles: list[Role], software_months: int | None) -> str | None:
    """junior | mid | senior | lead, from title words first and duration second."""
    software_roles = [r for r in roles if r.title_canonical != "non_software"]
    if not software_roles:
        return None
    titles = " ".join(r.title_raw.lower() for r in software_roles)
    if any(w in titles for w in _LEAD_WORDS):
        return "lead"
    if any(w in titles for w in _SENIOR_WORDS):
        return "senior"
    if any(w in titles for w in _JUNIOR_WORDS) and (software_months or 0) < 36:
        return "junior"
    if software_months is None:
        return None
    if software_months >= 84:
        return "senior"
    if software_months >= 36:
        return "mid"
    return "junior"


# --------------------------------------------------------------------------- #
# 7. Protected-attribute scrub
# --------------------------------------------------------------------------- #

def _walk_keys(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key), path
            yield from _walk_keys(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _walk_keys(value, f"{path}[{i}]")


def scrub(profile: Profile) -> Profile:
    """Assert no protected attribute is representable in the profile, then stamp the list.

    The schema makes these fields unrepresentable by construction; this is the belt to
    that braces, and it fails loudly rather than quietly dropping data.
    """
    dumped = profile.model_dump()
    forbidden = set(NEVER_EXTRACT)
    for key, parent in _walk_keys(dumped):
        # `never_extract` holds the list itself as values, not as keys.
        if key in forbidden and not parent.startswith("never_extract"):
            raise ProtectedFieldError(
                f"protected attribute key {key!r} present in profile at {parent or '<root>'!r}"
            )
    profile.never_extract = list(NEVER_EXTRACT)
    return profile


def _looks_like_phone(text: str) -> bool:
    return any(sum(c.isdigit() for c in m.group()) >= _MIN_PHONE_DIGITS
               for m in _PHONE_RE.finditer(text))


def pii_warnings(profile: Profile) -> list[str]:
    """Quotes that look like they dragged contact details in. Advisory, not fatal:
    the quote is provenance for a real value, so we flag it for review rather than
    dropping the value it supports."""
    warnings: list[str] = []
    for path, _env, evidence in _iter_evidence(profile):
        for ev in evidence:
            if _EMAIL_RE.search(ev.quote) or _looks_like_phone(ev.quote):
                warnings.append(f"{path}: quote contains contact details: {ev.quote[:70]!r}")
    return warnings


# --------------------------------------------------------------------------- #
# build_profile
# --------------------------------------------------------------------------- #

def _env(value: Any, derivation: str, confidence: Confidence,
         evidence: list[Evidence] | None = None) -> Envelope:
    return Envelope(
        value=value,
        derivation=derivation,  # type: ignore[arg-type]
        confidence=confidence,
        evidence=list(evidence or []),
    )


def _months_env(subset: list[Role]) -> Envelope:
    """Union of a role subset's intervals as a computed Envelope. An empty subset is a
    real, computed zero (no such roles); a non-empty subset with no usable dates is
    absent (we know the roles exist but not how long they lasted)."""
    if not subset:
        return _env(0, "computed", "medium")
    intervals = _intervals(subset)
    if not intervals:
        return Envelope.absent()
    return _env(union_months(intervals), "computed", _precision_confidence(subset))


def build_profile(
    raw: BaseModel,
    cv_text: str,
    *,
    as_of: str,
    manifest: Manifest,
    taxonomy: Taxonomy,
    provenance: Provenance,
) -> Profile:
    """Assemble a validated `Profile` from one `ExtractionOutput` plus the CV text."""
    index = QuoteIndex(cv_text)

    # 1-2. roles: dates, then evidence (an unverifiable role loses its dates)
    roles = verify_role_evidence(normalise_roles(raw.roles, as_of=as_of), index)

    # 3. taxonomy canonicalisation of what the model could not map
    recovered, leftover = _canonicalise_unmatched(raw.unmatched_skills, taxonomy)

    denied: dict[str, str] = {}
    for item in raw.denied_skills:
        denied.setdefault(_sid(item.skill), item.quote)
    block: dict[str, str] = {}
    for item in raw.skills_block:
        sid = _sid(item.skill)
        if sid not in denied:
            block.setdefault(sid, item.quote)

    project_skills: dict[str, str] = {}
    topic_counts: Counter[str] = Counter()
    projects: list[Project] = []
    for proj in raw.projects:
        projects.append(
            Project(
                title=proj.title,
                topics=list(dict.fromkeys(proj.topics)),
                skills=list(dict.fromkeys(_sid(s) for s in proj.skills)),
                deployed=_tri(proj.deployed),
                evidence=[Evidence(quote=proj.quote, section="projects")],
            )
        )
        topic_counts.update(dict.fromkeys(proj.topics).keys())
        for raw_sid in proj.skills:
            project_skills.setdefault(_sid(raw_sid), proj.quote)

    role_skills: dict[str, list[Role]] = defaultdict(list)
    for role in roles:
        for sid in role.skills_mentioned:
            role_skills[sid].append(role)

    projects_per_skill: Counter[str] = Counter()
    for proj in projects:
        projects_per_skill.update(dict.fromkeys(proj.skills).keys())

    software_roles = professional_roles(roles)
    backend_roles = [r for r in roles if r.is_backend_role]

    # 4. per-skill envelopes
    all_ids = (set(role_skills) | set(block) | set(denied)
               | set(recovered) | set(project_skills))
    skills: dict[str, SkillEntry] = {}
    for sid in sorted(all_ids):
        entry = SkillEntry()
        mentioning = role_skills.get(sid, [])

        if sid in denied:
            entry.held = _env(False, "denied", "high",
                              [Evidence(quote=denied[sid], section="denial")])
        else:
            evidence = [Evidence(quote=r.evidence[0].quote, section="experience")
                        for r in mentioning[:2] if r.evidence]
            if sid in block:
                evidence.append(Evidence(quote=block[sid], section="skills"))
            if not evidence and sid in project_skills:
                evidence.append(Evidence(quote=project_skills[sid], section="projects"))
            if evidence:
                entry.held = _env(True, "stated", "high", evidence)
            else:
                # Only reachable via `unmatched_skills`, which carries no quote.
                entry.held = _env(True, "stated", "low")

        # Months, recency and depth come from professional software roles only.
        professional = professional_roles(mentioning)
        months = None if sid in denied else skill_months(professional, sid)
        entry.dated = bool(professional) and sid not in denied
        if months is not None:
            entry.months = _env(months, "computed", _precision_confidence(professional))
            ends = [r.end for r in professional if r.end]
            if ends:
                entry.last_used_year = _env(int(max(ends)[:4]), "computed", "medium")

        if sid not in denied:
            value, conf = _proficiency(sid, software_roles, months)
            entry.proficiency = _env(value, "inferred", conf)

        entry.project_count = _env(projects_per_skill.get(sid, 0), "computed", "medium")
        skills[sid] = entry

    # 5. experience aggregates
    experience = Experience(
        roles=roles,
        total_months=_months_env(roles),
        software_months=_months_env(software_roles),
        backend_months=_months_env(backend_roles),
        num_roles=_env(len(roles), "computed", "high"),
    )
    seniority = infer_seniority(roles, experience.software_months.value)
    if seniority is not None:
        experience.seniority = _env(seniority, "inferred", "medium")

    # 6-7. the rest of the profile
    education = Education()
    edu_quote = _opt(raw.education.quote)
    edu_ev = [Evidence(quote=edu_quote, section="education")] if edu_quote else []
    level = _opt(raw.education.highest_level)
    if level is not None and level != "not_stated":
        education.highest_level = _env(level, "stated", "high", edu_ev)
    if _opt(raw.education.field) is not None:
        education.field = _env(_opt(raw.education.field), "stated", "medium", edu_ev)
    in_progress = _tri(raw.education.in_progress)
    if in_progress is not None:
        education.in_progress = _env(in_progress, "stated", "medium", edu_ev)

    eligibility = Eligibility()
    elig_quote = _opt(raw.eligibility.quote)
    elig_ev = [Evidence(quote=elig_quote, section="eligibility")] if elig_quote else []
    for field, coerce in (("work_authorization_region", _opt),
                          ("requires_sponsorship", _tri),
                          ("location_country", _opt),
                          ("relocation_willing", _tri)):
        value = coerce(getattr(raw.eligibility, field))
        if value is not None:
            setattr(eligibility, field, _env(value, "stated", "medium", elig_ev))

    profile = Profile(
        as_of=as_of,
        job_family=manifest.job_family,
        provenance=provenance,
        experience=experience,
        skills=skills,
        projects=projects,
        project_counts_by_topic=dict(sorted(topic_counts.items())),
        education=education,
        certifications=[
            Certification(
                cert_id=c.cert_id,
                issuer=c.issuer,
                issued=normalise_date(c.issued_raw, as_of)[0],
                evidence=[Evidence(quote=c.quote, section="certifications")],
            )
            for c in raw.certifications
        ],
        languages=[Language(lang=lg.lang, cefr=_opt(lg.cefr)) for lg in raw.languages],
        eligibility=eligibility,
        unmatched_skills=leftover,
    )

    verify_evidence(profile, cv_text)
    scrub(profile)
    recompute_derived(profile, manifest)
    return profile
