"""Profile-first synthetic data: sample the ground truth in pure Python.

The ordering is the whole trick (research/notes/cv_parsing_and_llm_brief.md 4.2):
we sample the truth here, with no LLM, and only afterwards ask Claude to render CV
prose from it. Labels produced by a model would make extraction accuracy
meaningless; labels produced by this module are exact by construction, because the
derived fields (per-skill months, total/software/backend months) are computed with
the *same* interval-union code (`recourse_screen.dates.union_months`) the extractor
postprocess is graded against.

Proficiency heuristic (must stay identical to the extractor postprocess):
    3 - the skill is a primary skill of a role lasting >= 24 months
    2 - the skill is a primary skill of any role, or its union months >= 12
    1 - the skill is merely mentioned in a role, or appears only in a skills list

Two deliberate hard cases are flagged in `meta`:
  * `under_report` (30%): ~30% of the role-mentioned skills are dropped from the
    rendered CV but kept in the truth. Recall on those is the honest ceiling of any
    parser and the headline finding of the evaluation.
  * `year_only_dates` (20%): the CV shows bare years. `dates.normalise_date` maps a
    bare year to mid-year ("2021" -> "2021-07"), so the truth intervals are snapped
    to YYYY-07 as well; the ground truth is then exactly what a perfect parser could
    recover from the rendered text, and the date-precision penalty shows up as
    genuine ambiguity rather than as a bookkeeping artefact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..dates import index_to_ym, interval_months, union_months, ym_to_index
from ..schemas import (
    Certification,
    Education,
    Eligibility,
    Envelope,
    Experience,
    Language,
    Profile,
    Project,
    Provenance,
    Role,
    SkillEntry,
)

# --------------------------------------------------------------------------- #
# Style directives (consumed by synth/render.py; stored in meta so a corpus can
# be regenerated or filtered by style).
# --------------------------------------------------------------------------- #

STYLES: list[str] = [
    "reverse-chronological with tight bullet points under each role, classic and plain",
    "terse startup one-pager: minimal punctuation, fragments, no filler, fits on one screen",
    "prose paragraphs with no bullet points at all; each role is a short narrative paragraph",
    "functional CV grouped by skill area first, with a bare employment-history list at the end",
    "academic style: formal register, long section headings, education before experience",
    "consultant two-pager: verbose, client-engagement framing, a profile summary paragraph on top",
    "non-native English: simple sentences, occasional article and preposition slips, no typos in "
    "proper nouns or dates",
    "Finnish-English mix: Finnish section headings (Työkokemus, Koulutus, Taidot, Projektit) with "
    "English body text",
]

EMPLOYERS = [
    "Nordcom Oy", "Vantaa Systems", "Helsinki Data Works", "Arctic Cloud Oy", "Sisu Software Oy",
    "Tampere Tech Group", "Kaiku Digital", "Polaris Payments", "Aurora Analytics Oy", "Lumi Labs",
    "Vireo Solutions", "Koski Engineering", "Saimaa Interactive", "Ruska Systems", "Nokka Oy",
]
NON_SOFTWARE_EMPLOYERS = [
    "Metsa Logistics Oy", "Suomi Retail Group", "Baltic Health Services", "Kanta Kirjasto",
    "Pohjola Hotels", "Turku Catering Oy", "Vihrea Puutarha Oy",
]
FREELANCE_EMPLOYERS = ["Self-employed (toiminimi)", "Freelance", "Independent contractor"]

FIELDS_OF_STUDY = [
    "Computer Science", "Software Engineering", "Information Technology", "Information Systems",
    "Electrical Engineering", "Mathematics", "Industrial Engineering and Management",
    "Business Administration", "Biology", "Communications",
]
CERTS = ["aws_saa", "cka", "ckad", "scrum_master", "istqb_foundation", "azure_az900"]
CERT_ISSUERS = {
    "aws_saa": "Amazon Web Services", "cka": "CNCF", "ckad": "CNCF",
    "scrum_master": "Scrum Alliance", "istqb_foundation": "ISTQB", "azure_az900": "Microsoft",
}


@dataclass
class Archetype:
    name: str
    weight: float
    seniority: str
    family: str  # RoleFamily for the software roles
    role_count: tuple[int, int]
    total_months: tuple[int, int]
    titles: dict[str, list[str]]  # junior|mid|senior -> titles
    core: list[str]
    growth: list[str]  # added to the newer roles
    pool: list[str]  # archetype-plausible extras
    topics: list[str]
    edu_weights: dict[str, float]
    career_change: bool = False
    extras_range: tuple[int, int] = (1, 4)  # rng.integers(low, high) -> 1..3
    project_range: tuple[int, int] = (0, 4)
    sponsorship_p: float = 0.15
    block_only_range: tuple[int, int] = (0, 4)
    families_override: list[str] = field(default_factory=list)


_BACKEND_TITLES = {
    "junior": ["Junior Backend Developer", "Backend Developer Trainee", "Graduate Software Engineer",
               "Software Developer Intern", "Junior Software Engineer"],
    "mid": ["Backend Developer", "Backend Software Engineer", "Software Engineer (Backend)",
            "Server-side Developer", "API Developer"],
    "senior": ["Senior Backend Engineer", "Lead Backend Developer", "Senior Software Engineer",
               "Principal Backend Engineer", "Backend Tech Lead"],
}
_FRONTEND_TITLES = {
    "junior": ["Junior Frontend Developer", "Web Developer Trainee", "Junior UI Developer"],
    "mid": ["Frontend Developer", "Frontend Engineer", "React Developer", "Web Developer"],
    "senior": ["Senior Frontend Engineer", "Lead Frontend Developer", "UI Architect"],
}
_QA_TITLES = {
    "junior": ["Junior QA Engineer", "Software Tester", "QA Trainee"],
    "mid": ["QA Engineer", "Test Automation Engineer", "QA Analyst"],
    "senior": ["Senior QA Engineer", "Test Automation Lead", "QA Lead"],
}
_DEVOPS_TITLES = {
    "junior": ["Junior DevOps Engineer", "Cloud Support Engineer", "IT Operations Trainee"],
    "mid": ["DevOps Engineer", "Cloud Infrastructure Engineer", "Platform Engineer"],
    "senior": ["Senior DevOps Engineer", "Site Reliability Engineer", "Head of Platform"],
}
_NON_SW_TITLES = {
    "junior": ["Customer Support Agent", "Shop Assistant", "Warehouse Associate"],
    "mid": ["Logistics Coordinator", "Customer Success Specialist", "Laboratory Technician",
            "Administrative Coordinator"],
    "senior": ["Retail Store Manager", "Operations Manager", "Team Lead, Customer Service"],
}

ARCHETYPES: list[Archetype] = [
    Archetype(
        name="junior_backend", weight=0.15, seniority="junior", family="backend_engineer",
        role_count=(1, 3), total_months=(8, 30), titles=_BACKEND_TITLES,
        core=["python", "git", "sql", "rest_api"],
        growth=["docker", "postgresql", "linux"],
        pool=["flask", "fastapi", "django", "nodejs", "mongodb", "pytest", "html_css", "agile", "oop"],
        topics=["backend", "tutorial", "other"],
        edu_weights={"secondary": 0.1, "vocational": 0.2, "bsc": 0.55, "msc": 0.15},
        project_range=(1, 4),
    ),
    Archetype(
        name="mid_backend", weight=0.20, seniority="mid", family="backend_engineer",
        role_count=(2, 4), total_months=(36, 84), titles=_BACKEND_TITLES,
        core=["python", "git", "postgresql", "rest_api", "docker"],
        growth=["ci_cd", "aws", "linux", "microservices"],
        pool=["django", "fastapi", "flask", "redis", "kafka", "nodejs", "typescript", "pytest",
              "github_actions", "nginx", "agile", "system_design"],
        topics=["backend", "microservices", "testing", "other"],
        edu_weights={"secondary": 0.05, "vocational": 0.15, "bsc": 0.5, "msc": 0.3},
    ),
    Archetype(
        name="senior_backend", weight=0.17, seniority="senior", family="backend_engineer",
        role_count=(2, 5), total_months=(90, 170), titles=_BACKEND_TITLES,
        core=["python", "git", "postgresql", "rest_api", "docker", "linux"],
        growth=["kubernetes", "aws", "ci_cd", "microservices", "terraform"],
        pool=["go", "java", "kafka", "redis", "grpc", "event_driven", "distributed_systems",
              "system_design", "helm", "prometheus", "grafana", "spring", "elasticsearch"],
        topics=["backend", "microservices", "infrastructure", "devops"],
        edu_weights={"vocational": 0.1, "bsc": 0.4, "msc": 0.45, "phd": 0.05},
        project_range=(1, 4),
    ),
    Archetype(
        name="frontend", weight=0.12, seniority="mid", family="frontend_engineer",
        role_count=(1, 4), total_months=(20, 90), titles=_FRONTEND_TITLES,
        core=["javascript", "html_css", "react", "git"],
        growth=["typescript", "nextjs", "nodejs"],
        pool=["vue", "angular", "rest_api", "graphql", "testing", "playwright", "agile", "nodejs"],
        topics=["frontend", "other", "tutorial"],
        edu_weights={"secondary": 0.1, "vocational": 0.25, "bsc": 0.45, "msc": 0.2},
    ),
    Archetype(
        name="qa", weight=0.09, seniority="mid", family="qa_engineer",
        role_count=(1, 4), total_months=(18, 96), titles=_QA_TITLES,
        core=["testing", "git", "selenium"],
        growth=["python", "ci_cd", "pytest"],
        pool=["playwright", "sql", "javascript", "jenkins", "agile", "docker", "rest_api"],
        topics=["testing", "other"],
        edu_weights={"secondary": 0.15, "vocational": 0.3, "bsc": 0.4, "msc": 0.15},
    ),
    Archetype(
        name="devops", weight=0.11, seniority="senior", family="devops_engineer",
        role_count=(2, 4), total_months=(50, 150), titles=_DEVOPS_TITLES,
        core=["linux", "docker", "bash", "git", "ci_cd"],
        growth=["kubernetes", "terraform", "aws", "prometheus"],
        pool=["ansible", "helm", "argo_cd", "gitlab_ci", "jenkins", "grafana", "nginx", "python",
              "azure", "gcp", "cloudformation"],
        topics=["devops", "infrastructure", "other"],
        edu_weights={"secondary": 0.1, "vocational": 0.35, "bsc": 0.4, "msc": 0.15},
    ),
    Archetype(
        name="non_software", weight=0.08, seniority="mid", family="non_software",
        role_count=(1, 4), total_months=(24, 140), titles=_NON_SW_TITLES,
        core=["excel", "agile"],
        growth=[],
        pool=["sql", "git", "html_css"],
        topics=["other"],
        edu_weights={"secondary": 0.3, "vocational": 0.35, "bsc": 0.3, "msc": 0.05},
        extras_range=(0, 2), project_range=(0, 2), block_only_range=(0, 3),
    ),
    Archetype(
        name="career_changer", weight=0.08, seniority="junior", family="backend_engineer",
        role_count=(2, 4), total_months=(40, 120), titles=_BACKEND_TITLES,
        core=["python", "git", "sql"],
        growth=["django", "docker", "postgresql", "rest_api"],
        pool=["flask", "html_css", "javascript", "linux", "pytest", "agile", "excel"],
        topics=["backend", "tutorial", "other"],
        edu_weights={"secondary": 0.15, "vocational": 0.25, "bsc": 0.4, "msc": 0.2},
        career_change=True, project_range=(1, 4), sponsorship_p=0.25,
    ),
]

_PROJECT_TITLES = {
    "backend": ["Recipe API with authentication", "Personal finance tracker backend",
                "URL shortener service", "Job-board REST API", "Booking service for a local gym"],
    "microservices": ["Order/payment split of a monolith", "Event-driven notification service",
                      "Multi-service e-commerce sandbox", "Inventory microservice with gRPC"],
    "frontend": ["Portfolio site with a component library", "Dashboard for public transport data",
                 "Recipe browser single-page app"],
    "testing": ["End-to-end test suite for a demo shop", "Flaky-test triage tooling",
                "Contract tests for a public API"],
    "devops": ["Home-lab cluster with monitoring", "Self-hosted CI runner setup",
               "Blue/green deployment playground"],
    "infrastructure": ["Terraform modules for a three-tier app", "Cost dashboard for a cloud account"],
    "data": ["Open-data ETL for Helsinki traffic", "Weather data warehouse experiment"],
    "machine_learning": ["Image classifier for plant species", "Text classifier for support tickets"],
    "mobile": ["Habit-tracking mobile app"],
    "tutorial": ["Course project: blog engine", "Bootcamp capstone: to-do app",
                 "Following a Django tutorial series"],
    "other": ["Volunteer website for a sports club", "Discord bot for a study group",
              "Spreadsheet automation for a small shop"],
}

_LANG_SETS = [
    [("Finnish", "native"), ("English", "C1")],
    [("Finnish", "native"), ("English", "B2"), ("Swedish", "B1")],
    [("English", "C2"), ("Russian", "native")],
    [("English", "C1"), ("Spanish", "native"), ("Finnish", "A2")],
    [("English", "B2"), ("Hindi", "native"), ("Finnish", "A1")],
    [("Finnish", "native"), ("English", "C2"), ("German", "B1")],
]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _pick(rng: np.random.Generator, seq: list) -> Any:
    return seq[int(rng.integers(0, len(seq)))]


def _pick_weighted(rng: np.random.Generator, options: list[str], weights: list[float]) -> str:
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    return str(rng.choice(np.asarray(options, dtype=object), p=w))


def _split_months(rng: np.random.Generator, total: int, n: int, min_each: int = 5) -> list[int]:
    """Split `total` months across `n` roles, each at least `min_each`."""
    if n <= 1:
        return [max(min_each, total)]
    shares = rng.dirichlet(np.ones(n) * 2.5)
    parts = [max(min_each, int(round(total * float(s)))) for s in shares]
    drift = total - sum(parts)
    i = 0
    while drift != 0 and i < 200:
        j = i % n
        if drift > 0:
            parts[j] += 1
            drift -= 1
        elif parts[j] > min_each:
            parts[j] -= 1
            drift += 1
        i += 1
    return parts


def _title_bucket(seniority: str, position: int, n_roles: int) -> str:
    """Older roles read more junior than newer ones."""
    if seniority in ("senior", "lead"):
        ladder = ["junior", "mid", "senior"]
    elif seniority == "mid":
        ladder = ["junior", "mid", "mid"]
    else:
        ladder = ["junior", "junior", "mid"]
    if n_roles == 1:
        return ladder[-1]
    frac = position / max(1, n_roles - 1)  # 0 = oldest
    return ladder[min(len(ladder) - 1, int(round(frac * (len(ladder) - 1))))]


def _named_in(sid: str, blob: str, taxonomy) -> bool:
    """True if the skill's id, label or any alias occurs as a whole word in `blob`."""
    concept = taxonomy.by_id.get(sid, {})
    names = [sid, concept.get("label", ""), *concept.get("aliases", [])]
    for n in names:
        n = (n or "").strip().lower()
        if len(n) < 2:
            continue
        if re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", blob):
            return True
    return False


def _snap_year(idx: int) -> int:
    """Snap an absolute month index to 1 July of its year (what `normalise_date`
    recovers from a bare-year string)."""
    return (idx // 12) * 12 + 6


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #

def sample_truth(
    rng: np.random.Generator,
    *,
    taxonomy,
    manifest,
    as_of: str,
    idx: int,
) -> tuple[Profile, dict]:
    """Sample one ground-truth profile plus its generation metadata.

    Returns `(profile, meta)` where meta is
    `{archetype, style, seniority, omitted_skills, overlap, year_only_dates,
      under_report, idx, source_file}`.
    """
    from ..derived import recompute_derived  # local: avoids an import cycle at module load

    arch = _pick_weighted(rng, [a.name for a in ARCHETYPES], [a.weight for a in ARCHETYPES])
    spec = next(a for a in ARCHETYPES if a.name == arch)

    under_report = bool(rng.random() < 0.30)
    year_only = bool(rng.random() < 0.20)
    overlap = bool(rng.random() < 0.25)
    style = _pick(rng, STYLES)

    n_roles = int(rng.integers(spec.role_count[0], spec.role_count[1] + 1))
    total_target = int(rng.integers(spec.total_months[0], spec.total_months[1] + 1))
    durations = _split_months(rng, total_target, n_roles, min_each=12 if year_only else 5)

    # ---- intervals, newest first, then reversed to chronological ---------- #
    as_of_idx = ym_to_index(as_of[:7])
    cursor = as_of_idx if rng.random() < 0.62 else as_of_idx - int(rng.integers(1, 7))
    spans: list[tuple[int, int]] = []
    for d in durations:  # durations[0] is the most recent role
        end_i = cursor
        start_i = end_i - d
        spans.append((start_i, end_i))
        gap = 0 if rng.random() < 0.75 else int(rng.integers(1, 5))
        cursor = start_i - gap
    spans.reverse()  # chronological, oldest first

    if year_only:
        snapped: list[tuple[int, int]] = []
        for s, e in spans:
            e2 = e if e == as_of_idx else _snap_year(e)
            s2 = _snap_year(s)
            if e2 <= s2:
                s2 = e2 - 12
            snapped.append((s2, e2))
        spans = snapped

    # ---- role families --------------------------------------------------- #
    families: list[str] = []
    for i in range(n_roles):
        if spec.career_change:
            # the oldest role(s) are outside software; the newest are in it
            switch_at = max(1, n_roles - int(rng.integers(1, max(2, n_roles))))
            families.append("non_software" if i < switch_at else spec.family)
        else:
            families.append(spec.family)
    if spec.career_change and spec.family not in families:
        families[-1] = spec.family

    fullstack_is_backend = bool(rng.random() < 0.5)

    # ---- skills per role -------------------------------------------------- #
    tax_ids = [i for i in taxonomy.ids]
    allowed_pool = [s for s in spec.pool if s in taxonomy.by_id]
    core = [s for s in spec.core if s in taxonomy.by_id]
    growth = [s for s in spec.growth if s in taxonomy.by_id]

    roles: list[Role] = []
    for i, ((s_i, e_i), fam) in enumerate(zip(spans, families)):
        start, end = index_to_ym(s_i), index_to_ym(e_i)
        bucket = _title_bucket(spec.seniority, i, n_roles)
        # nobody is a "Trainee" for four years: long roles carry a more senior title
        dur = e_i - s_i
        if dur >= 48 and bucket == "junior":
            bucket = "mid"
        if dur >= 84 and bucket == "mid" and spec.seniority in ("senior", "lead"):
            bucket = "senior"
        if fam == "non_software":
            title = _pick(rng, _NON_SW_TITLES[bucket])
            employer = _pick(rng, NON_SOFTWARE_EMPLOYERS)
            skills = [s for s in ["excel", "agile"] if s in taxonomy.by_id]
            if rng.random() < 0.3 and "sql" in taxonomy.by_id:
                skills.append("sql")
        else:
            title = _pick(rng, spec.titles[bucket])
            employer = _pick(rng, EMPLOYERS)
            skills = list(core)
            # newer roles accumulate the growth skills
            n_growth = int(round(len(growth) * (i + 1) / n_roles)) if growth else 0
            skills += growth[:n_growth]
            n_extra = int(rng.integers(spec.extras_range[0], spec.extras_range[1]))
            for _ in range(n_extra):
                cand = _pick(rng, allowed_pool or tax_ids)
                if cand in taxonomy.by_id and cand not in skills:
                    skills.append(cand)
            if rng.random() < 0.35:
                cand = _pick(rng, tax_ids)
                if cand not in skills:
                    skills.append(cand)

        # co-occurrence closure: stating kubernetes almost always implies docker
        for base in list(skills):
            for implied in manifest.cooccurrence.get(base, []):
                if implied in taxonomy.by_id and implied not in skills and rng.random() < 0.8:
                    skills.append(implied)

        n_primary = 1 if rng.random() < 0.45 else 2
        primary = [skills[int(k)] for k in rng.choice(len(skills), size=min(n_primary, len(skills)),
                                                      replace=False)] if skills else []

        is_backend = fam == "backend_engineer" or (fam == "fullstack_engineer" and fullstack_is_backend)
        roles.append(Role(
            title_raw=title, title_canonical=fam, employer=employer, start=start, end=end,
            date_precision="year" if year_only else "month",
            months=interval_months(start, end), is_backend_role=is_backend,
            skills_mentioned=skills, primary_skills=primary,
        ))

    # ---- optional overlapping freelance contract -------------------------- #
    if overlap and roles:
        host = roles[int(rng.integers(0, len(roles)))]
        h_s, h_e = ym_to_index(host.start), ym_to_index(host.end)
        if h_e - h_s >= 6:
            o_s = h_s + int(rng.integers(1, max(2, (h_e - h_s) // 2 + 1)))
            o_e = min(as_of_idx, o_s + int(rng.integers(6, 19)))
            if year_only:
                o_s, o_e = _snap_year(o_s), (o_e if o_e == as_of_idx else _snap_year(o_e))
                if o_e <= o_s:
                    o_e = o_s + 12
            if o_e > o_s:
                fam = spec.family if spec.family != "non_software" else "other_software"
                f_skills = [s for s in core if s in taxonomy.by_id][:3] or ["git"]
                roles.append(Role(
                    title_raw=_pick(rng, ["Freelance Backend Developer",
                                          "Independent Software Consultant",
                                          "Freelance Developer (contract)"]),
                    title_canonical=fam, employer=_pick(rng, FREELANCE_EMPLOYERS),
                    start=index_to_ym(o_s), end=index_to_ym(o_e),
                    date_precision="year" if year_only else "month",
                    months=interval_months(index_to_ym(o_s), index_to_ym(o_e)),
                    is_backend_role=(fam == "backend_engineer"),
                    skills_mentioned=f_skills, primary_skills=f_skills[:1],
                ))
        else:
            overlap = False
    else:
        overlap = False

    roles.sort(key=lambda r: ym_to_index(r.start), reverse=True)  # reverse-chronological, as on a CV

    # ---- projects --------------------------------------------------------- #
    role_skills = sorted({s for r in roles for s in r.skills_mentioned})
    n_projects = int(rng.integers(spec.project_range[0], spec.project_range[1]))
    projects: list[Project] = []
    used_titles: set[str] = set()
    for _ in range(n_projects):
        topic = _pick(rng, spec.topics)
        titles = _PROJECT_TITLES.get(topic, _PROJECT_TITLES["other"])
        title = _pick(rng, titles)
        if title in used_titles:
            continue
        used_titles.add(title)
        topics = [topic]
        if rng.random() < 0.25 and topic != "backend":
            topics.append("backend")
        pool = role_skills or core
        k = min(len(pool), int(rng.integers(1, 4)))
        p_skills = [pool[int(j)] for j in rng.choice(len(pool), size=k, replace=False)] if pool else []
        projects.append(Project(title=title, topics=topics, skills=p_skills,
                                deployed=bool(rng.random() < 0.4)))

    project_counts: dict[str, int] = {}
    for p in projects:
        for t in p.topics:
            project_counts[t] = project_counts.get(t, 0) + 1

    # ---- skills block: some skills appear ONLY in the list (undated) ------- #
    n_block_only = int(rng.integers(spec.block_only_range[0], spec.block_only_range[1]))
    block_only: list[str] = []
    for _ in range(n_block_only):
        cand = _pick(rng, allowed_pool or tax_ids)
        if cand not in role_skills and cand not in block_only:
            block_only.append(cand)

    # ---- derived truth: same code path the extractor postprocess uses ------ #
    skills: dict[str, SkillEntry] = {}
    for sid in sorted(set(role_skills) | set(block_only)):
        mentioning = [r for r in roles if sid in r.skills_mentioned]
        dated = bool(mentioning)
        months = union_months([(r.start, r.end) for r in mentioning]) if dated else None
        prim_roles = [r for r in mentioning if sid in r.primary_skills]
        if any((r.months or 0) >= 24 for r in prim_roles):
            prof = 3
        elif prim_roles or (months is not None and months >= 12):
            prof = 2
        else:
            prof = 1
        last_year = max((int(r.end[:4]) for r in mentioning), default=None)
        p_count = sum(1 for p in projects if sid in p.skills)
        skills[sid] = SkillEntry(
            held=Envelope(value=True, derivation="stated", confidence="high"),
            months=(Envelope(value=months, derivation="computed", confidence="medium")
                    if dated else Envelope.absent()),
            last_used_year=(Envelope(value=last_year, derivation="computed", confidence="medium")
                            if last_year is not None else Envelope.absent()),
            proficiency=Envelope(value=prof, derivation="inferred", confidence="low"),
            project_count=Envelope(value=p_count, derivation="computed", confidence="medium"),
            dated=dated,
        )

    all_iv = [(r.start, r.end) for r in roles]
    sw_iv = [(r.start, r.end) for r in roles if r.title_canonical != "non_software"]
    be_iv = [(r.start, r.end) for r in roles if r.is_backend_role]
    experience = Experience(
        roles=roles,
        total_months=Envelope(value=union_months(all_iv), derivation="computed", confidence="medium"),
        software_months=Envelope(value=union_months(sw_iv), derivation="computed", confidence="medium"),
        backend_months=Envelope(value=union_months(be_iv), derivation="computed", confidence="medium"),
        seniority=Envelope(value=spec.seniority, derivation="inferred", confidence="medium"),
        num_roles=Envelope(value=len(roles), derivation="computed", confidence="high"),
    )

    # ---- education, certifications, languages, eligibility ---------------- #
    levels = list(spec.edu_weights.keys())
    level = _pick_weighted(rng, levels, [spec.edu_weights[k] for k in levels])
    in_progress = bool(rng.random() < 0.12)
    education = Education(
        highest_level=Envelope(value=level, derivation="stated", confidence="high"),
        field=Envelope(value=_pick(rng, FIELDS_OF_STUDY), derivation="stated", confidence="high"),
        in_progress=Envelope(value=in_progress, derivation="stated" if in_progress else "absent",
                             confidence="medium" if in_progress else "low"),
    )

    certifications: list[Certification] = []
    if rng.random() < 0.35:
        cid = _pick(rng, CERTS)
        certifications.append(Certification(cert_id=cid, issuer=CERT_ISSUERS[cid],
                                            issued=index_to_ym(as_of_idx - int(rng.integers(3, 48)))))

    languages = [Language(lang=l, cefr=c) for l, c in _pick(rng, _LANG_SETS)]

    sponsorship = bool(rng.random() < spec.sponsorship_p)
    country = _pick_weighted(rng, ["FI", "FI", "FI", "EE", "SE"], [0.6, 0.15, 0.1, 0.09, 0.06])
    eligibility = Eligibility(
        work_authorization_region=Envelope(value="non-EU" if sponsorship else "EU",
                                           derivation="stated" if sponsorship else "inferred",
                                           confidence="medium"),
        requires_sponsorship=Envelope(value=sponsorship,
                                      derivation="stated" if sponsorship else "inferred",
                                      confidence="medium" if sponsorship else "low"),
        location_country=Envelope(value=country, derivation="stated", confidence="high"),
        relocation_willing=(Envelope(value=True, derivation="stated", confidence="medium")
                            if rng.random() < 0.3 else Envelope.absent()),
    )

    profile = Profile(
        as_of=as_of,
        provenance=Provenance(
            cv_sha256="synthetic", source_file=f"synth_{idx:03d}.txt", extractor_model="truth",
            prompt_version="synth-v1", taxonomy_version=taxonomy.version, extracted_at=as_of,
        ),
        experience=experience, skills=skills, projects=projects,
        project_counts_by_topic=project_counts, education=education,
        certifications=certifications, languages=languages, eligibility=eligibility,
    )
    recompute_derived(profile, manifest)

    # ---- under-reporting: drop ~30% of the role-mentioned skills from the
    # RENDER only. They stay in the truth; recall on them is the honest ceiling.
    omitted: list[str] = []
    if under_report and role_skills:
        # A skill named by a role or project title cannot honestly be "omitted": the
        # title is a raw fact the renderer must print verbatim, so a "QA Engineer"
        # always leaks `testing` through the alias "qa". Excluding those keeps the
        # omitted-recall number measuring what it claims to measure.
        blob = " ".join([r.title_raw or "" for r in roles]
                        + [r.employer or "" for r in roles]
                        + [p.title for p in projects]).lower()
        candidates = [s for s in role_skills if not _named_in(s, blob, taxonomy)]
        if candidates:
            n_omit = max(1, int(round(0.30 * len(role_skills))))
            picks = rng.choice(len(candidates), size=min(n_omit, len(candidates)), replace=False)
            omitted = sorted(candidates[int(j)] for j in picks)

    meta = {
        "idx": idx,
        "source_file": f"synth_{idx:03d}.txt",
        "archetype": arch,
        "style": style,
        "seniority": spec.seniority,
        "omitted_skills": omitted,
        "overlap": overlap,
        "year_only_dates": year_only,
        "under_report": bool(under_report and omitted),
        "block_only_skills": block_only,
        "n_roles": len(roles),
    }
    return profile, meta


def sample_corpus(n: int, seed: int, *, taxonomy=None, manifest=None,
                  as_of: str | None = None) -> list[tuple[Profile, dict]]:
    """Sample `n` profiles. Each index gets its own child generator, so profile i
    is identical whether you sample 5 or 500."""
    from .. import config
    from ..loaders import load_manifest, load_taxonomy

    taxonomy = taxonomy or load_taxonomy()
    manifest = manifest or load_manifest("software_engineering.json")
    as_of = as_of or config.AS_OF
    seq = np.random.SeedSequence(seed)
    out = []
    for i, child in enumerate(seq.spawn(n)):
        out.append(sample_truth(np.random.default_rng(child), taxonomy=taxonomy,
                                manifest=manifest, as_of=as_of, idx=i))
    return out
