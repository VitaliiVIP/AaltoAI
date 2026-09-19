"""Shared pydantic models: candidate profile, feature manifest, job template,
recourse outputs and API contracts. Every other module builds against these.

Design rules (from research/design_report.md):
- Every profile leaf is an Envelope carrying derivation + evidence.
- Actionability lives in the manifest (employer policy), never in the profile.
- Protected attributes are not representable in the profile at all.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# --------------------------------------------------------------------------- #
# Envelope
# --------------------------------------------------------------------------- #

Derivation = Literal["stated", "computed", "inferred", "absent", "denied", "restated"]
Confidence = Literal["high", "medium", "low"]


class Evidence(BaseModel):
    quote: str
    start: int | None = None
    end: int | None = None
    section: str | None = None
    verified: bool | None = None  # set by postprocess via substring match


class Envelope(BaseModel):
    value: Any = None
    derivation: Derivation = "absent"
    confidence: Confidence = "low"
    evidence: list[Evidence] = Field(default_factory=list)

    @classmethod
    def absent(cls) -> Envelope:
        return cls()

    @property
    def is_known(self) -> bool:
        return self.derivation not in ("absent", "denied") and self.value is not None


# --------------------------------------------------------------------------- #
# Candidate profile
# --------------------------------------------------------------------------- #

DatePrecision = Literal["month", "year", "unknown"]

# Canonical role families. `non_software` roles never count toward software_months.
RoleFamily = Literal[
    "backend_engineer", "frontend_engineer", "fullstack_engineer", "devops_engineer",
    "data_engineer", "ml_engineer", "mobile_engineer", "qa_engineer", "embedded_engineer",
    "other_software", "non_software",
]

ProjectTopic = Literal[
    "backend", "frontend", "microservices", "data", "machine_learning", "mobile",
    "devops", "infrastructure", "testing", "tutorial", "other",
]

EducationLevel = Literal["none", "secondary", "vocational", "bsc", "msc", "phd"]
EDUCATION_LADDER: list[str] = ["none", "secondary", "vocational", "bsc", "msc", "phd"]

NEVER_EXTRACT: list[str] = [
    "name", "date_of_birth", "age", "gender", "photo", "nationality", "marital_status",
    "street_address", "postal_code", "health", "religion", "union_membership",
    "criminal_record", "graduation_year", "employment_gaps",
]


class Role(BaseModel):
    title_raw: str
    title_canonical: RoleFamily
    employer: str | None = None
    start: str | None = None  # "YYYY-MM" after normalisation
    end: str | None = None  # "YYYY-MM"; "present" resolved to AS_OF by postprocess
    date_precision: DatePrecision = "unknown"
    months: int | None = None  # computed
    is_backend_role: bool = False
    skills_mentioned: list[str] = Field(default_factory=list)  # taxonomy ids
    primary_skills: list[str] = Field(default_factory=list)  # in title or first two bullets
    evidence: list[Evidence] = Field(default_factory=list)


class Experience(BaseModel):
    roles: list[Role] = Field(default_factory=list)
    total_months: Envelope = Field(default_factory=Envelope)
    software_months: Envelope = Field(default_factory=Envelope)
    backend_months: Envelope = Field(default_factory=Envelope)
    seniority: Envelope = Field(default_factory=Envelope)  # junior|mid|senior|lead
    num_roles: Envelope = Field(default_factory=Envelope)


class SkillEntry(BaseModel):
    held: Envelope = Field(default_factory=Envelope)  # bool
    months: Envelope = Field(default_factory=Envelope)  # int, union of role intervals
    last_used_year: Envelope = Field(default_factory=Envelope)
    proficiency: Envelope = Field(default_factory=Envelope)  # 0..3
    project_count: Envelope = Field(default_factory=Envelope)
    dated: bool = False  # False => only in a skills list, months is null


class Project(BaseModel):
    title: str
    topics: list[ProjectTopic] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    deployed: bool | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class Education(BaseModel):
    highest_level: Envelope = Field(default_factory=Envelope)  # EducationLevel
    field: Envelope = Field(default_factory=Envelope)
    in_progress: Envelope = Field(default_factory=Envelope)


class Certification(BaseModel):
    cert_id: str
    issuer: str | None = None
    issued: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class Language(BaseModel):
    lang: str
    cefr: str | None = None
    derivation: Derivation = "stated"
    confidence: Confidence = "medium"


class Eligibility(BaseModel):
    work_authorization_region: Envelope = Field(default_factory=Envelope)
    requires_sponsorship: Envelope = Field(default_factory=Envelope)
    location_country: Envelope = Field(default_factory=Envelope)
    relocation_willing: Envelope = Field(default_factory=Envelope)


class Provenance(BaseModel):
    cv_sha256: str
    source_file: str | None = None
    extractor_model: str
    prompt_version: str
    taxonomy_version: str
    extracted_at: str


class Profile(BaseModel):
    schema_version: str = "1.0"
    job_family: str = "software_engineering"
    as_of: str
    provenance: Provenance
    experience: Experience = Field(default_factory=Experience)
    skills: dict[str, SkillEntry] = Field(default_factory=dict)  # keyed by taxonomy id
    projects: list[Project] = Field(default_factory=list)
    project_counts_by_topic: dict[str, int] = Field(default_factory=dict)
    education: Education = Field(default_factory=Education)
    certifications: list[Certification] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    eligibility: Eligibility = Field(default_factory=Eligibility)
    # Computed by postprocess from the manifest's `derived` rules, e.g. cloud_platform_held.
    derived: dict[str, Envelope] = Field(default_factory=dict)
    unmatched_skills: list[str] = Field(default_factory=list)
    never_extract: list[str] = Field(default_factory=lambda: list(NEVER_EXTRACT))

    # ---- path access ---------------------------------------------------- #
    def resolve(self, path: str) -> Envelope:
        """Resolve a manifest feature path to an Envelope. Missing skills/topics
        resolve to an absent Envelope, never to an error."""
        parts = path.split(".")
        head = parts[0]
        if head == "skills" and len(parts) == 3:
            entry = self.skills.get(parts[1])
            if entry is None:
                return Envelope.absent()
            return getattr(entry, parts[2])
        if head == "project_counts_by_topic" and len(parts) == 2:
            if parts[1] in self.project_counts_by_topic:
                return Envelope(value=self.project_counts_by_topic[parts[1]],
                                derivation="computed", confidence="medium")
            return Envelope(value=0, derivation="computed", confidence="medium")
        if head == "derived" and len(parts) == 2:
            return self.derived.get(parts[1], Envelope.absent())
        if head in ("experience", "education", "eligibility") and len(parts) == 2:
            return getattr(getattr(self, head), parts[1])
        if head == "certifications" and len(parts) == 2:
            held = any(c.cert_id == parts[1] for c in self.certifications)
            return Envelope(value=held, derivation="stated" if held else "absent",
                            confidence="high" if held else "low")
        raise KeyError(f"unresolvable profile path: {path}")

    def set_path(self, path: str, env: Envelope) -> None:
        """Write an Envelope at a manifest path (used by restatement)."""
        parts = path.split(".")
        head = parts[0]
        if head == "skills" and len(parts) == 3:
            entry = self.skills.setdefault(parts[1], SkillEntry())
            setattr(entry, parts[2], env)
            return
        if head == "project_counts_by_topic" and len(parts) == 2:
            self.project_counts_by_topic[parts[1]] = int(env.value or 0)
            return
        if head == "derived" and len(parts) == 2:
            self.derived[parts[1]] = env
            return
        if head in ("experience", "education", "eligibility") and len(parts) == 2:
            setattr(getattr(self, head), parts[1], env)
            return
        raise KeyError(f"unsettable profile path: {path}")


# --------------------------------------------------------------------------- #
# Feature manifest (employer policy, static, per job family)
# --------------------------------------------------------------------------- #

Actionability = Literal["actionable", "conditionally_actionable", "immutable", "protected_never_use"]
FeatureType = Literal["bool", "int", "ordinal"]


class StepSpec(BaseModel):
    unit: str  # "boolean" | "months" | "projects" | "level" | ...
    size: int = 1  # raw units per solver step (e.g. 6 months per step)


class DerivedRule(BaseModel):
    """How postprocess computes a `derived.<name>` boolean: true if any listed path is truthy."""
    any_of: list[str]
    phrase: str


class FeatureSpec(BaseModel):
    type: FeatureType
    step: StepSpec
    domain_max: int  # in steps
    ladder: list[str] | None = None  # ordinal only
    actionability: Actionability
    direction: Literal["increase_only", "none"] = "increase_only"
    cost_per_step: int | None = None  # None for immutable / protected
    max_delta: int = 0  # steps reachable within manifest.horizon_months
    typical_time_months: int | None = None
    is_causal: bool = True
    candidate_phrase: str
    disclosure: str | None = None  # immutable only: fixed text shown verbatim
    reason: str | None = None  # protected_never_use: why

    @property
    def solver_may_move(self) -> bool:
        return (self.actionability in ("actionable", "conditionally_actionable")
                and self.is_causal and self.direction == "increase_only" and self.max_delta > 0)


class Manifest(BaseModel):
    job_family: str
    version: str
    horizon_months: int = 18
    features: dict[str, FeatureSpec]
    derived: dict[str, DerivedRule] = Field(default_factory=dict)
    # stated skill id -> skills that almost always travel with it
    cooccurrence: dict[str, list[str]] = Field(default_factory=dict)
    # Causal / dependency constraints. These are facts about how the world works
    # ("Kubernetes implies Docker"), not employer value judgements, so they live
    # here with the rest of the domain model rather than in a job template.
    dependencies: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_dependencies(self) -> Manifest:
        for d in self.dependencies:
            Dependency.parse(d)
        return self

    @property
    def parsed_dependencies(self) -> list[Dependency]:
        return [Dependency.parse(r) for r in self.dependencies]

    def protected_paths(self) -> set[str]:
        return {p for p, f in self.features.items() if f.actionability == "protected_never_use"}


# --------------------------------------------------------------------------- #
# Job template
# --------------------------------------------------------------------------- #

_KO_RE = re.compile(r"^\s*([\w.]+)\s*(==|>=|<=|>|<)\s*(\S+)\s*$")
_DEP_LEVEL_RE = re.compile(r"^\s*x'\[([\w.]+)\]\s*<=\s*x'\[([\w.]+)\]\s*$")
_DEP_DELTA_RE = re.compile(r"^\s*delta\[([\w.]+)\]\s*<=\s*(-?\d+)\s*(?:\+\s*(\d+)\s*\*\s*delta\[([\w.]+)\])?\s*$")


def _parse_literal(s: str) -> Any:
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s.strip("'\"")


class Knockout(BaseModel):
    rule: str
    path: str
    op: Literal["==", ">=", "<=", ">", "<"]
    value: Any

    @classmethod
    def parse(cls, rule: str) -> Knockout:
        m = _KO_RE.match(rule)
        if not m:
            raise ValueError(f"bad knockout rule: {rule!r}")
        return cls(rule=rule, path=m.group(1), op=m.group(2), value=_parse_literal(m.group(3)))

    def holds(self, raw_value: Any, spec: FeatureSpec | None = None) -> bool:
        """Evaluate the rule against a raw profile value.

        An ordinal is compared by its position on the manifest's ladder, never as
        a string: ``"none" >= "bsc"`` is true alphabetically and false in every
        sense an employer means.
        """
        if raw_value is None:
            return False
        v, t = raw_value, self.value
        if isinstance(v, bool) or isinstance(t, bool):
            return (bool(v) == bool(t)) if self.op == "==" else False
        if spec is not None and spec.type == "ordinal":
            ladder = spec.ladder or []
            if v not in ladder or t not in ladder:
                return False
            v, t = ladder.index(v), ladder.index(t)
        return {"==": v == t, ">=": v >= t, "<=": v <= t, ">": v > t, "<": v < t}[self.op]


class Dependency(BaseModel):
    """Two supported linear forms:
    level_le:  x'[a] <= x'[b]                (in steps)
    delta_le:  delta[a] <= c + k*delta[b]    (in steps; k/b optional)
    """
    rule: str
    kind: Literal["level_le", "delta_le"]
    a: str
    b: str | None = None
    c: int = 0
    k: int = 0

    @classmethod
    def parse(cls, rule: str) -> Dependency:
        m = _DEP_LEVEL_RE.match(rule)
        if m:
            return cls(rule=rule, kind="level_le", a=m.group(1), b=m.group(2))
        m = _DEP_DELTA_RE.match(rule)
        if m:
            return cls(rule=rule, kind="delta_le", a=m.group(1), c=int(m.group(2)),
                       k=int(m.group(3) or 0), b=m.group(4))
        raise ValueError(f"bad dependency rule: {rule!r}")

    def gloss(self, manifest: Manifest) -> str:
        """Plain English, generated from the rule itself. The UI must never carry
        a hand-written gloss per rule: one would go stale the moment a rule moves."""
        def phrase(path: str | None) -> str:
            if not path:
                return ""
            spec = manifest.features.get(path)
            return spec.candidate_phrase if spec else path

        if self.kind == "level_le":
            return f"{phrase(self.a).capitalize()} cannot be credited beyond {phrase(self.b)}."
        unit = (manifest.features[self.a].step.unit
                if self.a in manifest.features else "steps")
        allowance = f"{self.c} more ({unit})" if self.c else "no increase"
        if self.b and self.k:
            return (f"{phrase(self.a).capitalize()} can gain {allowance} on its own, "
                    f"plus {self.k} for every step of {phrase(self.b)}.")
        return f"{phrase(self.a).capitalize()} is limited to {allowance}."


class ScoreTerm(BaseModel):
    """One line of the employer's point budget.

    ``points`` is the authoring unit: the share of the 100-point budget this
    criterion is worth at full marks.  ``weight`` is the engine unit: points per
    solver step, kept integral so CP-SAT stays exact.  Authoring in points and
    deriving the weight means nobody has to know that a year of experience is
    two six-month steps.

    Exactly one of the two is written by hand.  When ``points`` is given,
    :meth:`JobTemplate.bind` fills ``weight`` in once the manifest is known (the
    cap can default to the feature's ``domain_max``, which only the manifest has).
    """

    weight: int = 0  # per step; integers keep CP-SAT exact. Derived when `points` is set.
    points: int | None = None  # share of the 100-point budget at full marks
    cap: int | None = None  # in steps; None => domain_max
    absent_prior: int = 0  # steps credited when the field is absent (unverified, not zero)

    @model_validator(mode="after")
    def _one_authoring_unit(self) -> ScoreTerm:
        if self.points is not None and self.weight:
            raise ValueError("set either points (budget share) or weight (per step), not both")
        if self.points is not None and self.points < 0:
            raise ValueError("points cannot be negative")
        return self


class ModeA(BaseModel):
    threshold: int
    margin_eps: int = 0
    weight_shrink_rho: int = 0


class ModeB(BaseModel):
    slots_N: int = 3
    margin_eps: int = 0
    weight_shrink_rho: int = 0


class Modes(BaseModel):
    A: ModeA
    B: ModeB


BUDGET_TOTAL = 100  # the employer's whole point budget, so a score reads as a percentage


class JobTemplate(BaseModel):
    job_id: str
    title: str
    family: str
    manifest: str  # filename under manifests/
    version: str = "v1"
    knockouts: list[str] = Field(default_factory=list)
    score: dict[str, ScoreTerm]
    mode: Modes
    # Deprecated: causal constraints belong to the manifest (see Manifest.dependencies).
    # Still accepted so older job files and fixtures keep loading.
    dependencies: list[str] = Field(default_factory=list)
    k_routes: int = 3
    sparsity_lambda: int = 1
    solver_time_limit_s: float = 10.0
    bound: bool = False  # set by bind(); points-authored terms have no weight until then

    @model_validator(mode="after")
    def _validate_rules(self) -> JobTemplate:
        for r in self.knockouts:
            Knockout.parse(r)
        for d in self.dependencies:
            Dependency.parse(d)
        return self

    @property
    def parsed_knockouts(self) -> list[Knockout]:
        return [Knockout.parse(r) for r in self.knockouts]

    @property
    def parsed_dependencies(self) -> list[Dependency]:
        return [Dependency.parse(r) for r in self.dependencies]

    @property
    def uses_budget(self) -> bool:
        return any(t.points is not None for t in self.score.values())

    def cap_of(self, path: str, manifest: Manifest) -> int:
        term = self.score[path]
        return manifest.features[path].domain_max if term.cap is None else term.cap

    def bind(self, manifest: Manifest) -> JobTemplate:
        """Resolve the point budget into per-step weights. Idempotent.

        A criterion worth ``points`` at full marks, reached in ``cap`` steps, is
        worth ``points / cap`` per step.  That has to divide exactly or the
        budget would not add up to what the employer published, so a remainder
        is an error here rather than a silent rounding downstream -- the
        authoring UI snaps to realisable values so HR never sees this.
        """
        if self.bound:
            return self
        budget = 0
        for path, term in self.score.items():
            if term.points is None:
                continue
            if path not in manifest.features:
                raise KeyError(f"job {self.job_id!r} scores unknown manifest feature: {path}")
            cap = self.cap_of(path, manifest)
            if cap <= 0:
                raise ValueError(f"{path}: cap is {cap}; a scored feature needs at least one step")
            if term.points % cap:
                ok = [n for n in range(cap, term.points + 2 * cap, cap)]
                raise ValueError(
                    f"{path}: {term.points} points does not divide into {cap} steps; "
                    f"nearest realisable values are {ok[-3:]}"
                )
            term.weight = term.points // cap
            budget += term.points
        if self.uses_budget and budget != BUDGET_TOTAL:
            raise ValueError(
                f"job {self.job_id!r}: the point budget sums to {budget}, not {BUDGET_TOTAL}"
            )
        self.bound = True
        return self

    def points_of(self, path: str, manifest: Manifest) -> int:
        """What a criterion is worth at full marks, whichever unit it was authored in."""
        term = self.score[path]
        return term.points if term.points is not None else term.weight * self.cap_of(path, manifest)


def effective_dependencies(job: JobTemplate, manifest: Manifest) -> list[Dependency]:
    """Every causal constraint in force, manifest first.

    The manifest is the home for these. The job-level list is legacy and stays
    supported only so job files written before the move keep working.
    """
    return manifest.parsed_dependencies + job.parsed_dependencies


# --------------------------------------------------------------------------- #
# Feature vector (profile projected through manifest + job)
# --------------------------------------------------------------------------- #

class FeatureValue(BaseModel):
    path: str
    steps: int  # integer solver units
    raw_value: Any  # months / bool / level name / count
    derivation: Derivation
    confidence: Confidence
    prior_applied: bool = False  # absent_prior was used


FeatureVector = dict[str, FeatureValue]


# --------------------------------------------------------------------------- #
# Scoring and recourse outputs
# --------------------------------------------------------------------------- #

class KnockoutResult(BaseModel):
    rule: str
    path: str
    passed: bool
    current_value: Any
    actionability: Actionability


class FeatureContribution(BaseModel):
    path: str
    phrase: str
    steps: int
    cap: int
    weight: int
    contribution: int
    max_contribution: int
    raw_value: Any
    derivation: Derivation
    prior_applied: bool = False


class Decision(BaseModel):
    mode: Literal["A", "B"]
    passed: bool
    score: int
    knockouts_passed: bool
    knockouts: list[KnockoutResult]
    threshold: int  # mode A: tau; mode B: bar score the candidate needed
    margin_eps: int = 0
    # mode B only
    rank: int | None = None
    pool_size: int | None = None
    slots_n: int | None = None
    max_score: int = 0


class Delta(BaseModel):
    delta_id: str
    field: str
    from_value: Any
    to_value: Any
    from_steps: int
    to_steps: int
    unit: str
    derivation_of_current: Derivation
    candidate_phrase: str
    typical_time_months: int | None
    actionability: Actionability
    cost: int


class Route(BaseModel):
    route_id: str
    deltas: list[Delta]
    cost: int
    total_time_months: int
    new_score: int
    flip_test_passed: bool
    # mode B only: rank the candidate would have had in this pool with the new score
    rank: int | None = None


class ImmutableBlocker(BaseModel):
    field: str
    rule: str
    current_value: Any
    disclosure: str


class NoFeasiblePath(BaseModel):
    reason: str
    gap_remaining: int
    partial_progress: Route | None = None


class RestatementHint(BaseModel):
    field: str
    phrase: str
    because_of: str  # stated skill that makes this one likely
    zero_cost: bool = True


class Sentence(BaseModel):
    delta_id: str
    sentence: str


class Explanation(BaseModel):
    text: str
    sentences: list[Sentence] = Field(default_factory=list)
    checks_passed: bool
    fallback_used: bool
    check_failures: list[str] = Field(default_factory=list)
    model_version: str


class ScreenResult(BaseModel):
    decision_id: str
    candidate_id: str
    job_id: str
    mode: Literal["A", "B"]
    as_of: str
    versions: dict[str, str]
    profile: Profile
    feature_contributions: list[FeatureContribution]
    decision: Decision
    routes: list[Route] = Field(default_factory=list)
    immutable_blockers: list[ImmutableBlocker] = Field(default_factory=list)
    restatement_hints: list[RestatementHint] = Field(default_factory=list)
    no_feasible_path: NoFeasiblePath | None = None
    explanation: Explanation | None = None
    aggregate_line: str | None = None  # mode B: "3 of 10 advanced"
    assertions: dict[str, bool] = Field(default_factory=dict)


class Confirmation(BaseModel):
    path: str
    value: Any


class RestateRequest(BaseModel):
    candidate_id: str
    job_id: str = "backend_engineer"
    # Mode B is the default: "we interview five" is how hiring actually works, and
    # it is the harder case for recourse, so it should not be the one you opt into.
    mode: Literal["A", "B"] = "B"
    N: int | None = None
    confirmations: list[Confirmation]


class ScreenRequest(BaseModel):
    candidate_id: str | None = None
    cv_text: str | None = None
    job_id: str = "backend_engineer"
    mode: Literal["A", "B"] = "B"
    N: int | None = None
    explain: bool = True


class AuditRecord(BaseModel):
    decision_id: str
    timestamp: str
    prev_hash: str
    hash: str = ""
    payload: dict[str, Any]
