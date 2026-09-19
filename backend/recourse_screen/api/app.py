"""FastAPI surface for the separate frontend, plus a throwaway demo page at /."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import config, pipeline
from ..audit.log import get_record, read_records, verify_chain
from ..loaders import list_jobs, load_job, manifest_for_job
from ..schemas import RestateRequest, ScreenRequest, ScreenResult

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Recourse pre-screener", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/jobs")
def jobs() -> list[dict]:
    out = []
    for jid in list_jobs():
        job = load_job(jid)
        man = manifest_for_job(job)
        feats = {}
        for path, term in job.score.items():
            spec = man.features[path]
            feats[path] = {
                "phrase": spec.candidate_phrase, "weight": term.weight,
                "cap": term.cap if term.cap is not None else spec.domain_max,
                "absent_prior": term.absent_prior, "unit": spec.step.unit, "step_size": spec.step.size,
                "actionability": spec.actionability, "cost_per_step": spec.cost_per_step,
                "max_delta": spec.max_delta, "typical_time_months": spec.typical_time_months,
                "is_causal": spec.is_causal,
            }
        out.append({
            "job_id": job.job_id, "title": job.title, "version": job.version,
            "knockouts": job.knockouts, "score": feats, "mode": job.mode.model_dump(),
            "dependencies": job.dependencies, "k_routes": job.k_routes,
            "horizon_months": man.horizon_months, "manifest_version": man.version,
            "protected_never_use": sorted(man.protected_paths()),
        })
    return out


@app.get("/candidates")
def candidates(job: str = "backend_engineer", mode: str = "A", N: int | None = None) -> list[dict]:
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
    from ..extract.pdf import pdf_to_text

    if file is not None:
        raw = await file.read()
        name = file.filename or "upload"
        if name.lower().endswith(".pdf"):
            tmp = config.DATA_DIR / "uploads" / name
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(raw)
            text = pdf_to_text(tmp)
        else:
            text = raw.decode("utf-8", errors="replace")
        source = Path(name).stem + ".txt"
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
