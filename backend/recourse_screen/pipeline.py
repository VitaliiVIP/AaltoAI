"""End-to-end orchestration: profile -> score -> recourse -> explanation -> audit.

The LLM appears only in extract (LLM #1) and explain (LLM #2). Everything in
between is deterministic and replayable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import config
from .audit.log import append_record, make_payload
from .loaders import (list_cached_profiles, load_job, load_profile, manifest_for_job)
from .schemas import (Confirmation, Explanation, JobTemplate, Manifest, Profile,
                      RestateRequest, ScreenResult)


def versions() -> dict[str, str]:
    return {
        "schema": config.SCHEMA_VERSION,
        "taxonomy": config.TAXONOMY_VERSION,
        "extract_prompt": config.EXTRACT_PROMPT_VERSION,
        "explain_prompt": config.EXPLAIN_PROMPT_VERSION,
        "scorer": config.SCORER_VERSION,
        "solver": config.SOLVER_VERSION,
        "model": config.MODEL_ID,
    }


def load_pool() -> list[tuple[str, Profile]]:
    """All cached demo profiles (candidate_id, Profile). This is the mode-B pool."""
    return [(cid, load_profile(p)) for cid, p in list_cached_profiles().items()]


def candidate_profile(candidate_id: str) -> Profile:
    paths = list_cached_profiles()
    if candidate_id not in paths:
        raise KeyError(f"unknown candidate_id {candidate_id!r}; known: {sorted(paths)}")
    return load_profile(paths[candidate_id])


def screen_profile(
    profile: Profile,
    *,
    candidate_id: str,
    job_id: str = "backend_engineer",
    mode: str = "A",
    N: int | None = None,
    explain: bool = True,
    pool: list[tuple[str, Profile]] | None = None,
    write_audit: bool = True,
    parent_decision_id: str | None = None,
) -> ScreenResult:
    from .explain.generate import generate_explanation
    from .recourse.ranking_mode import run_ranking_mode
    from .recourse.threshold_mode import run_threshold_mode
    from .restate import restatement_hints

    job: JobTemplate = load_job(job_id)
    manifest: Manifest = manifest_for_job(job)

    if mode == "B":
        pool = pool if pool is not None else load_pool()
        # make sure the candidate (possibly a restated copy) is in the pool under its id
        pool = [(cid, p) for cid, p in pool if cid != candidate_id] + [(candidate_id, profile)]
        outcome = run_ranking_mode(profile, job, manifest, pool, candidate_id, N=N)
    else:
        outcome = run_threshold_mode(profile, job, manifest)

    explanation: Explanation | None = None
    if not outcome.decision.passed:
        explanation = generate_explanation(
            decision=outcome.decision,
            routes=outcome.routes,
            immutable_blockers=outcome.immutable_blockers,
            no_feasible_path=outcome.no_feasible_path,
            as_of=profile.as_of,
            model_version=f"{job.version}/{config.SCORER_VERSION}",
            use_llm=explain,
        )

    hints = restatement_hints(profile, manifest, job)

    decision_id = "unaudited"
    if write_audit:
        payload = make_payload(
            outcome,
            mode=mode,
            job=job,
            manifest=manifest,
            profile=profile,
            candidate_id=candidate_id,
            cv_sha256=profile.provenance.cv_sha256,
            explanation_hash=(hashlib.sha256(explanation.text.encode()).hexdigest() if explanation else None),
            versions=versions(),
        )
        if parent_decision_id:
            payload["parent_decision_id"] = parent_decision_id
        decision_id = append_record(payload).decision_id

    return ScreenResult(
        decision_id=decision_id,
        candidate_id=candidate_id,
        job_id=job.job_id,
        mode=mode,  # type: ignore[arg-type]
        as_of=profile.as_of,
        versions=versions(),
        profile=profile,
        feature_contributions=outcome.contributions,
        decision=outcome.decision,
        routes=outcome.routes,
        immutable_blockers=outcome.immutable_blockers,
        restatement_hints=hints,
        no_feasible_path=outcome.no_feasible_path,
        explanation=explanation,
        aggregate_line=outcome.aggregate_line,
        assertions=outcome.assertions,
    )


def screen_candidate(candidate_id: str, **kw) -> ScreenResult:
    return screen_profile(candidate_profile(candidate_id), candidate_id=candidate_id, **kw)


def screen_cv_text(cv_text: str, *, source_file: str | None = None, **kw) -> ScreenResult:
    from .extract.extractor import extract_profile

    profile = extract_profile(cv_text, source_file=source_file)
    cid = Path(source_file).stem if source_file else profile.provenance.cv_sha256[:12]
    return screen_profile(profile, candidate_id=cid, **kw)


def restate(req: RestateRequest, *, explain: bool = True,
            parent_decision_id: str | None = None) -> ScreenResult:
    """Candidate confirms fields the screen missed; everything re-runs."""
    from .restate import apply_confirmations

    job = load_job(req.job_id)
    manifest = manifest_for_job(job)
    base = candidate_profile(req.candidate_id)
    patched = apply_confirmations(base, [Confirmation(**c.model_dump()) for c in req.confirmations], manifest)
    return screen_profile(patched, candidate_id=req.candidate_id, job_id=req.job_id, mode=req.mode,
                          N=req.N, explain=explain, parent_decision_id=parent_decision_id)
