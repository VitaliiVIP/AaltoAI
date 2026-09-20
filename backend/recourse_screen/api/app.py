"""FastAPI surface for the separate frontend, plus a throwaway demo page at /."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import config, pipeline
from ..audit.log import get_record, read_records, verify_chain
from ..authoring import catalogue_for, store
from ..emailer import EmailError, send_email
from ..loaders import (
    list_cached_profiles,
    list_jobs,
    load_cv_text,
    load_job,
    manifest_for_job,
)
from ..schemas import (
    BUDGET_TOTAL,
    RestateRequest,
    ScreenRequest,
    ScreenResult,
    SendEmailRequest,
    SendEmailResult,
)

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Recourse pre-screener", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


def _job_summary(jid: str) -> dict:
    job = load_job(jid)
    man = manifest_for_job(job)
    feats = {}
    for path, term in job.score.items():
        spec = man.features[path]
        cap = job.cap_of(path, man)
        feats[path] = {
            "phrase": spec.candidate_phrase,
            # `points` is what the criterion is worth at full marks and what the
            # employer actually chose; `weight` is the per-step figure the engine
            # runs on. Both ship so the UI never has to re-derive either.
            "points": job.points_of(path, man),
            "weight": term.weight, "cap": cap,
            "full_marks_at": _full_marks_at(spec, cap),
            "absent_prior": term.absent_prior, "unit": spec.step.unit, "step_size": spec.step.size,
            "actionability": spec.actionability, "cost_per_step": spec.cost_per_step,
            "max_delta": spec.max_delta, "typical_time_months": spec.typical_time_months,
            "is_causal": spec.is_causal, "type": spec.type,
        }
    return {
        "job_id": job.job_id, "title": job.title, "version": job.version,
        "family": job.family, "manifest": Path(job.manifest).name,
        "knockouts": job.knockouts, "score": feats, "mode": job.mode.model_dump(),
        # Causal constraints live in the manifest now. They ship with a generated
        # gloss so the UI never carries a hand-written sentence per rule.
        "dependencies": [
            {"rule": d.rule, "gloss": d.gloss(man)}
            for d in (man.parsed_dependencies + job.parsed_dependencies)
        ],
        "k_routes": job.k_routes,
        "budget_total": BUDGET_TOTAL,
        "horizon_months": man.horizon_months, "manifest_version": man.version,
        "protected_never_use": sorted(man.protected_paths()),
    }


def _full_marks_at(spec, cap: int):
    """The cap expressed in the feature's own unit, for display."""
    from ..score.features import steps_to_raw

    return steps_to_raw(spec, cap)


@app.get("/jobs")
def jobs() -> list[dict]:
    return [_job_summary(jid) for jid in list_jobs()]


@app.get("/candidates")
def candidates(job: str = "data_scientist", mode: str = "B", N: int | None = None) -> list[dict]:
    """Score and rank the whole pool. No LLM calls, no audit writes.

    Carries enough per-candidate detail (experience, the two largest shortfalls)
    for a list UI to render honestly before anything has been screened.
    """
    from ..score.features import build_feature_vector
    from ..score.scorer import evaluate_knockouts, score_vector

    jt = load_job(job)
    man = manifest_for_job(jt)
    pool = pipeline.load_pool()

    scored = []
    for cid, prof in pool:
        fv = build_feature_vector(prof, jt, man)
        score, contributions = score_vector(fv, jt, man)
        ko = all(k.passed for k in evaluate_knockouts(fv, jt, man))
        scored.append((cid, prof, score, contributions, ko))

    n = N or jt.mode.B.slots_N
    ranked = sorted(scored, key=lambda t: (not t[4], -t[2]))
    # Ties are pessimistic -- an equal score counts as ahead -- to match
    # recourse.ranking_mode._rank_of, so a card and its detail panel agree.
    qualified = [(s, ko) for _, _, s, _, ko in scored]

    rows = []
    for cid, prof, score, contributions, ko in ranked:
        rank = None
        if ko:
            rank = 1 + sum(1 for other_score, other_ko in qualified
                           if other_ko and other_score >= score) - 1
        passed = ko and (rank is not None and rank <= n) if mode == "B" else ko and score >= jt.mode.A.threshold
        gaps = sorted(
            (c for c in contributions if c.contribution < c.max_contribution),
            key=lambda c: c.max_contribution - c.contribution,
            reverse=True,
        )
        rows.append({
            "candidate_id": cid,
            "file": prof.provenance.source_file,
            # True when the API holds the PDF (an upload); the demo pool's files
            # ship with the frontend instead, so the UI picks the URL by this.
            "has_pdf": _upload_path(cid, ".pdf") is not None,
            "score": score,
            "knockouts_passed": ko,
            "rank": rank,
            "decision": "advance" if passed else "not_advanced",
            "total_months": prof.experience.total_months.value,
            "software_months": prof.experience.software_months.value,
            "top_gaps": [
                {"phrase": c.phrase, "missed": c.max_contribution - c.contribution,
                 "derivation": c.derivation}
                for c in gaps[:2]
            ],
        })
    return rows


@app.get("/candidates/{candidate_id}/cv")
def candidate_cv(candidate_id: str, job: str = "data_scientist") -> dict:
    """The CV text and every attribute read out of it, tied together by offsets.

    No LLM call: this is the stored parse replayed, not a second reading. The
    text is the same string the extractor saw, so `evidence.start`/`end` index
    straight into it and the UI never has to search for a quote.
    """
    from .attributes import attributes_for

    try:
        text = load_cv_text(candidate_id)
        profile = pipeline.candidate_profile(candidate_id)
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(404, f"no stored CV text for {candidate_id!r}") from e
    jt = load_job(job)
    return {
        "candidate_id": candidate_id,
        "text": text,
        "attributes": attributes_for(profile, manifest_for_job(jt), jt),
        # Read off the CV for addressing a reply, never scored (see Profile.contact_email).
        "contact_email": profile.contact_email,
        # Skills the CV named that the taxonomy has no concept for. Shown rather
        # than dropped: "we read this and could not use it" is part of the parse.
        "unmatched_skills": profile.unmatched_skills,
        "provenance": profile.provenance.model_dump(mode="json"),
    }


@app.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: str) -> dict:
    """Remove any candidate from the pool: cached text, parsed profile, raw
    extraction, and the original file if one was stored. Applies to the
    built-in demo set too -- those files are git-tracked, so deleting one
    here only removes it from the working tree; `git checkout` restores it."""
    profiles = list_cached_profiles()
    if candidate_id not in profiles:
        raise HTTPException(404, f"unknown candidate_id {candidate_id!r}")

    profile_path = profiles[candidate_id]
    sha = profile_path.stem
    for p in (
        config.CV_TEXT_DIR / f"{candidate_id}.txt",
        profile_path,
        config.DATA_DIR / "profiles_raw" / f"{sha}.json",
        config.UPLOADS_DIR / f"{candidate_id}.pdf",
        config.UPLOADS_DIR / f"{candidate_id}.png",
    ):
        p.unlink(missing_ok=True)
    return {"ok": True, "candidate_id": candidate_id}


def _upload_path(candidate_id: str, suffix: str) -> Path | None:
    """`UPLOADS_DIR/<candidate_id><suffix>` if that file exists, else None.

    The id is a filename stem straight off the URL, so anything that is not a
    plain single-segment name is refused rather than resolved.
    """
    if not candidate_id or candidate_id.startswith(".") or Path(candidate_id).name != candidate_id:
        return None
    path = config.UPLOADS_DIR / f"{candidate_id}{suffix}"
    return path if path.is_file() else None


@app.get("/candidates/{candidate_id}/file.pdf")
def candidate_pdf(candidate_id: str) -> FileResponse:
    """The uploaded PDF itself. Demo CVs are not here: they are static files
    in the frontend build, and the pool row's `has_pdf` says which is which."""
    path = _upload_path(candidate_id, ".pdf")
    if path is None:
        raise HTTPException(404, f"no PDF on file for {candidate_id!r}")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/candidates/{candidate_id}/thumbnail.png")
def candidate_thumbnail(candidate_id: str) -> FileResponse:
    """First page of the uploaded PDF as a PNG, for the card. Rendered lazily
    when missing, so uploads that predate thumbnails get one on first view."""
    from ..extract.pdf import PdfExtractionError, pdf_to_png

    png = _upload_path(candidate_id, ".png")
    if png is None:
        pdf = _upload_path(candidate_id, ".pdf")
        if pdf is None:
            raise HTTPException(404, f"no PDF on file for {candidate_id!r}")
        try:
            png = pdf_to_png(pdf, pdf.with_suffix(".png"))
        except PdfExtractionError as e:
            raise HTTPException(404, f"could not render a thumbnail: {e}") from e
    return FileResponse(png, media_type="image/png")


@app.get("/jobs/{job_id}/spec")
def job_spec(job_id: str) -> dict:
    """The editable form of a job: points, knockouts, threshold. Nothing else."""
    try:
        return store.current_spec(job_id).model_dump()
    except FileNotFoundError as e:
        raise HTTPException(404, f"no such job: {job_id}") from e


@app.get("/catalogue")
def catalogue(job: str | None = None, manifest: str = "data_science.json") -> dict:
    """What a job can be built out of: every usable feature, and what is refused.

    This is the source for the hard-requirement checklist and the point budget
    editor, so the UI never has to know a manifest path or a rule syntax.
    """
    from ..loaders import load_manifest

    if job is not None:
        jt = load_job(job)
        return catalogue_for(manifest_for_job(jt), jt)
    return catalogue_for(load_manifest(manifest))


@app.post("/jobs/preflight")
def jobs_preflight(spec: store.JobSpec) -> dict:
    """Check a draft without saving it: what the budget becomes, and what is wrong."""
    return store.preflight(spec)


@app.post("/jobs")
def jobs_save(spec: store.JobSpec) -> dict:
    """Validate and write a job template. Returns the saved job as /jobs renders it."""
    try:
        store.save(spec)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return _job_summary(spec.job_id)


@app.post("/jobs/draft")
def jobs_draft(body: dict) -> dict:
    """Draft a job configuration from a pasted job ad. One LLM call, nothing saved.

    The response carries the refusals and unmapped requirements alongside the
    spec: a draft that silently dropped half the ad would look like agreement.
    """
    from ..authoring.draft import DraftError, draft_from_ad

    ad = str(body.get("ad_text") or "")
    try:
        return draft_from_ad(
            ad,
            manifest_name=str(body.get("manifest") or "data_science.json"),
            job_id=body.get("job_id") or None,
            threshold=int(body.get("threshold") or 80),
            slots_n=int(body.get("slots_n") or 3),
        )
    except DraftError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/screen")
def screen(req: ScreenRequest) -> ScreenResult:
    try:
        if req.candidate_id:
            return pipeline.screen_candidate(req.candidate_id, job_id=req.job_id, mode=req.mode,
                                             N=req.N, explain=req.explain)
        if req.cv_text:
            return pipeline.screen_cv_text(req.cv_text, job_id=req.job_id, mode=req.mode,
                                           N=req.N, explain=req.explain)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    raise HTTPException(400, "candidate_id or cv_text required")


@app.post("/extract")
async def extract(file: UploadFile | None = None, cv_text: str | None = None) -> dict:
    from ..extract.extractor import extract_profile
    from ..extract.pdf import PdfExtractionError, pdf_to_png, pdf_to_text, sha256_text

    if file is not None:
        raw = await file.read()
        # Basename only: the client picks this string, and it becomes both the
        # candidate_id and the file stem under data/.
        name = Path(file.filename or "upload").name
        stem = Path(name).stem
        if not stem or stem.startswith("."):
            raise HTTPException(400, "the upload needs a filename")
        if name.lower().endswith(".pdf"):
            # Kept at <candidate_id>.pdf, which is where /candidates/{id}/file.pdf
            # and the thumbnail route look for it.
            pdf = config.UPLOADS_DIR / f"{stem}.pdf"
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(raw)
            try:
                text = pdf_to_text(pdf)
            except PdfExtractionError as e:
                # The upload's stored path means nothing to whoever sees the toast.
                raise HTTPException(400, str(e).replace(str(pdf), name)) from e
            try:
                pdf_to_png(pdf, pdf.with_suffix(".png"))
            except PdfExtractionError:
                pass  # the card falls back to initials; the parse still goes ahead
        else:
            text = raw.decode("utf-8", errors="replace")
        source = f"{stem}.txt"
        # The profile cache is keyed by the sha of the CV *text*, and re-extracting
        # rewrites that entry's source_file -- so uploading a CV already in the pool
        # would rename the sitting candidate out from under the list. Refuse instead.
        sha = sha256_text(text)
        for cid, cached in list_cached_profiles().items():
            if cached.stem == sha:
                raise HTTPException(409, f"This CV is already in the pool as {cid}.")
        # keep the text so the candidate shows up in the pool list next time
        (config.CV_TEXT_DIR / source).write_text(text)
    elif cv_text:
        text, source = cv_text, None
    else:
        raise HTTPException(400, "file or cv_text required")
    profile = extract_profile(text, source_file=source)
    return {"candidate_id": Path(source).stem if source else profile.provenance.cv_sha256[:12],
            "profile": profile.model_dump(mode="json")}


@app.post("/restate")
def restate(req: RestateRequest, parent_decision_id: str | None = None, explain: bool = True) -> ScreenResult:
    try:
        return pipeline.restate(req, explain=explain, parent_decision_id=parent_decision_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@app.post("/send-email")
def send_email_route(req: SendEmailRequest) -> SendEmailResult:
    """Real SMTP send — see recourse_screen/emailer.py. Defaults to a disposable
    Ethereal Email sandbox, so nothing here ever reaches a real inbox unless
    SMTP_* in backend/.env is pointed at a real provider."""
    try:
        result = send_email(req.to, req.subject, req.body)
    except EmailError as e:
        raise HTTPException(502, str(e)) from e
    return SendEmailResult(**result)


@app.get("/audit")
def audit() -> dict:
    ok, n, bad = verify_chain()
    recs = read_records()
    return {"chain_ok": ok, "count": n, "first_bad_index": bad,
            "records": [r.model_dump(mode="json") for r in recs[-50:]]}


@app.get("/audit/{decision_id}")
def audit_one(decision_id: str) -> dict:
    rec = get_record(decision_id)
    if rec is None:
        raise HTTPException(404, "no such decision")
    return rec.model_dump(mode="json")
