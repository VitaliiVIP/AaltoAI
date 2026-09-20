"""The editable surface of a job, and how it gets back onto disk.

``JobSpec`` is what the authoring UI posts: points rather than per-step weights,
knockouts as rules, and nothing else. It is deliberately a smaller surface than
:class:`~recourse_screen.schemas.JobTemplate` — ``solver_time_limit_s`` and the
robustness knobs are not HR's to set, and causal constraints belong to the
manifest — so the things HR can change are exactly the things HR is accountable
for.

Saving goes through :func:`build` first, which normalises the budget and then
constructs a real ``JobTemplate``. A spec that cannot become a working job never
reaches the filesystem.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .. import config
from ..loaders import load_job, load_manifest, manifest_for_job
from ..schemas import BUDGET_TOTAL, JobTemplate, Manifest, ScoreTerm
from . import budget

__all__ = ["JobSpec", "ScoreLine", "build", "preflight", "save", "spec_from_job"]

HEADER = """\
# Employer-authored job template.
#
# Scoring is a {total}-point budget: `points` is what a criterion is worth at full
# marks and the column adds up to {total}, so a score reads as a percentage and the
# threshold is a share of the job rather than a magic number. `cap` is how many
# solver steps count as full marks. Causal constraints are not here -- they are
# facts about the world and live in the manifest.
"""


class ScoreLine(BaseModel):
    points: int = Field(ge=0)
    cap: int | None = None
    absent_prior: int = 0


class JobSpec(BaseModel):
    job_id: str
    title: str
    family: str
    manifest: str
    version: str = "v1"
    knockouts: list[str] = Field(default_factory=list)
    score: dict[str, ScoreLine]
    threshold: int = 80          # mode A, as a share of the budget
    slots_n: int = 3             # mode B
    k_routes: int = 1
    sparsity_lambda: int = 1


def spec_from_job(job: JobTemplate, manifest: Manifest) -> JobSpec:
    return JobSpec(
        job_id=job.job_id,
        title=job.title,
        family=job.family,
        manifest=Path(job.manifest).name,
        version=job.version,
        knockouts=list(job.knockouts),
        score={
            path: ScoreLine(
                points=job.points_of(path, manifest),
                cap=term.cap,
                absent_prior=term.absent_prior,
            )
            for path, term in job.score.items()
        },
        threshold=job.mode.A.threshold,
        slots_n=job.mode.B.slots_N,
        k_routes=job.k_routes,
        sparsity_lambda=job.sparsity_lambda,
    )


def build(spec: JobSpec, manifest: Manifest | None = None) -> tuple[JobTemplate, dict[str, int]]:
    """Spec -> a bound ``JobTemplate``, plus the budget as it was actually allocated.

    The returned allocation may differ from what was asked for: :mod:`.budget`
    snaps each figure onto a value the scorer can represent and settles the
    remainder. Callers should show the employer what they ended up with.
    """
    mf = manifest or load_manifest(spec.manifest)

    unknown = sorted(set(spec.score) - set(mf.features))
    if unknown:
        raise KeyError(f"not declared by manifest {mf.version}: {', '.join(unknown)}")
    protected = sorted(set(spec.score) & mf.protected_paths())
    if protected:
        raise ValueError(
            f"cannot score protected attributes: {', '.join(protected)}"
        )

    caps = {
        path: max(1, line.cap if line.cap is not None else mf.features[path].domain_max)
        for path, line in spec.score.items()
    }
    allocation = budget.normalise({p: l.points for p, l in spec.score.items()}, caps)

    job = JobTemplate(
        job_id=spec.job_id,
        title=spec.title,
        family=spec.family,
        manifest=spec.manifest,
        version=spec.version,
        knockouts=spec.knockouts,
        score={
            path: ScoreTerm(
                points=points,
                cap=spec.score[path].cap,
                absent_prior=spec.score[path].absent_prior,
            )
            for path, points in allocation.items()
        },
        mode={  # type: ignore[arg-type]
            "A": {"threshold": spec.threshold},
            "B": {"slots_N": spec.slots_n},
        },
        k_routes=spec.k_routes,
        sparsity_lambda=spec.sparsity_lambda,
    )
    return job.bind(mf), allocation


def preflight(spec: JobSpec, manifest: Manifest | None = None) -> dict:
    """Check a spec without saving it. Never raises for a fixable problem.

    Returns the normalised allocation and a list of plain-English problems, so
    the UI can show what would happen before anything is written.
    """
    mf = manifest or load_manifest(spec.manifest)
    problems: list[str] = []
    try:
        job, allocation = build(spec, mf)
    except (KeyError, ValueError) as exc:
        return {"ok": False, "problems": [str(exc)], "allocation": {}, "threshold": spec.threshold}

    if spec.threshold > BUDGET_TOTAL:
        problems.append(
            f"the threshold ({spec.threshold}) is above the whole budget ({BUDGET_TOTAL}); "
            "nobody can clear it"
        )
    if spec.threshold <= 0:
        problems.append("a threshold of zero advances every candidate who clears the knockouts")

    # A rule that would raise from deep inside the solver becomes a sentence here.
    for ko in job.parsed_knockouts:
        if ko.path not in mf.features:
            problems.append(f"hard requirement on an unknown feature: {ko.path}")
            continue
        spec_f = mf.features[ko.path]
        if spec_f.actionability == "protected_never_use":
            problems.append(f"hard requirement on a protected attribute: {ko.path}")

    changed = {
        p: (spec.score[p].points, allocation.get(p, 0))
        for p in spec.score
        if spec.score[p].points != allocation.get(p, 0)
    }
    return {
        "ok": not problems,
        "problems": problems,
        "allocation": allocation,
        "adjusted": {p: {"asked": a, "applied": b} for p, (a, b) in changed.items()},
        "threshold": spec.threshold,
        "max_score": sum(allocation.values()),
    }


def _yaml_body(job: JobTemplate) -> str:
    doc = {
        "job_id": job.job_id,
        "title": job.title,
        "family": job.family,
        "manifest": Path(job.manifest).name,
        "version": job.version,
        "knockouts": list(job.knockouts),
        "score": {
            path: {
                k: v
                for k, v in (
                    ("points", term.points),
                    ("cap", term.cap),
                    ("absent_prior", term.absent_prior or None),
                )
                if v is not None
            }
            for path, term in job.score.items()
        },
        "mode": {
            "A": {"threshold": job.mode.A.threshold, "margin_eps": job.mode.A.margin_eps,
                  "weight_shrink_rho": job.mode.A.weight_shrink_rho},
            "B": {"slots_N": job.mode.B.slots_N, "margin_eps": job.mode.B.margin_eps,
                  "weight_shrink_rho": job.mode.B.weight_shrink_rho},
        },
        "k_routes": job.k_routes,
        "sparsity_lambda": job.sparsity_lambda,
    }
    # default_flow_style=None keeps leaf mappings inline, so a score line stays
    # one readable row instead of four.
    return HEADER.format(total=BUDGET_TOTAL) + yaml.safe_dump(
        doc, sort_keys=False, default_flow_style=None, width=100, allow_unicode=True
    )


def save(spec: JobSpec) -> Path:
    """Validate, write, and drop the loader caches so the next read sees it."""
    mf = load_manifest(spec.manifest)
    job, _ = build(spec, mf)
    path = config.JOBS_DIR / f"{job.job_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_yaml_body(job))
    # load_job/load_manifest are lru_cached; without this the API keeps serving
    # the version it read at startup.
    load_job.cache_clear()
    load_manifest.cache_clear()
    return path


def current_spec(job_id: str) -> JobSpec:
    job = load_job(job_id)
    return spec_from_job(job, manifest_for_job(job))
