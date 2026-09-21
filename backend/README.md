# Recourse pre-screener — backend

Demo backend for the AaltoAI hiring pre-screener with algorithmic recourse. Design:
`../research/design_report.md`. Decisions taken for this build are in the plan summary at the top of
that report's implementation (see git history) and in the module docstrings.

Pipeline: CV text → Claude structured extraction (LLM #1) → deterministic post-processing → enveloped
profile → knockouts ∧ additive scorer → CP-SAT minimum-cost recourse (cheapest route, flip-tested)
→ Claude one-sentence-per-delta verbalisation (LLM #2) → code-only checker → hash-chained audit log.

Both model calls happen offline, from scripts, and their outputs are committed under `data/`. The
API only ever reads those caches: it is a public, long-running demo and has no code path that
spends a token. The live-call code stays in `extract/extractor.py`, `explain/verbaliser.py` and
`authoring/draft.py` (a job-ad drafter, LLM #3, no longer exposed anywhere).

## Setup

```bash
cd backend
uv sync                       # Python 3.12+, installs ortools/anthropic/fastapi/...
cp .env.example .env          # ANTHROPIC_API_KEY only matters for the cache-filling scripts
```

## Run

```bash
uv run pytest                                     # deterministic tests, no LLM calls
uv run python scripts/extract_demo_cvs.py         # LLM-extract data/cv_text/*.txt -> data/profiles/ (cached)
uv run python scripts/cache_explanations.py --pool '^cv[0-9]+_'   # LLM sentences for every demo decision -> data/explanations/
uv run uvicorn recourse_screen.api.app:app --reload   # http://localhost:8000/docs (API only; the UI is ../frontend)
uv run python scripts/run_eval.py --n 30          # synthetic corpus + parser/recourse metrics -> data/synth/eval_report.md
```

`data/explanations/` is keyed by the exact prompt, which includes the job version and, in mode B,
the candidate's rank and the pool. Re-run `cache_explanations.py` after changing the job, the pool
or the explain prompt, or the affected decisions fall back to the templates. `--dry-run` says what
would be generated; `--pool` restricts the mode-B pool to the shipped demo set so a CV dropped in
locally does not shift everyone's rank.

The synthetic evaluation corpus committed under `data/synth/` predates the switch to the Data
Scientist job: its archetypes are software engineers, so the *parser* metrics still measure what
they claim to, while the *recourse* metrics read low because few of those candidates fit a data
science role. Regenerating it means new archetypes in `synth/sampler.py` and a paid re-render.

Add a CV: drop a PDF into `../frontend/public/assets/cvs/` and run
`pdftotext -layout file.pdf data/cv_text/file.txt`, then re-run the extraction script (only new files
call the API; profiles are cached by content hash) and `cache_explanations.py` (a new candidate
changes every mode-B rank).

## API (consumed by the React frontend in `../frontend/src`)

| Endpoint | Purpose |
|---|---|
| `GET /jobs` | Job templates with knockouts, weights, caps, costs, mode settings (the audit artefact) |
| `GET /candidates?job=&mode=A|B&N=` | Pool with score, knockouts, rank, decision, experience months and the two largest shortfalls. No LLM calls, no audit writes. |
| `POST /screen {candidate_id, job_id, mode, N, explain}` | Full `ScreenResult`: profile with evidence, contributions, decision, routes, blockers, hints, explanation. `explain` picks cached model sentences over the templates; it never triggers a call |
| `POST /restate {candidate_id, job_id, mode, N, confirmations:[{path,value}]}` | Candidate confirms missed fields; everything re-runs, new audit record linked to the parent |
| `GET /audit`, `GET /audit/{decision_id}` | Hash-chained records, chain verification |

The frontend (`npm run dev`, :5173) proxies `/api` here. There is no upload, no "polish" and no
draft-from-ad endpoint any more: those were the three places the API spent tokens, and a public
demo cannot have them. The candidate pool is whatever `data/cv_text/` + `data/profiles/` hold.

Likewise nothing on the API mutates shared state except the audit log: `POST /send-email`,
`DELETE /candidates/{id}` and `POST /jobs` (save) are gone, because every visitor shares one pool,
one job and one Mailgun domain. The UI still has Send, Delete and Save buttons; they act on the
browser session only. The code stays in `emailer.py` and `authoring/store.py`.

Schemas: `recourse_screen/schemas.py`. Employer configuration: `recourse_screen/jobs/*.yaml` and
`recourse_screen/manifests/*.json` (actionability, costs, horizons, causal dependencies).

`recourse_screen/jobs/` holds the shipped defaults and is read-only; the job editor writes to
`data/jobs/`, where a file of the same id shadows the default. Only `data/` is mounted as a volume
in the container, so that split is what keeps authored jobs alive across deploys.

## Layout

```
recourse_screen/
  schemas.py loaders.py config.py dates.py derived.py
  taxonomy/ manifests/ jobs/
  extract/   pdf.py prompts.py extractor.py postprocess.py
  score/     features.py scorer.py
  recourse/  solver.py threshold_mode.py ranking_mode.py outcome.py
  explain/   whitelist.py templates.py verbaliser.py checker.py generate.py
  explain/   cache.py (the on-disk sentence cache the API reads)
  restate.py audit/log.py pipeline.py api/app.py
  synth/     sampler.py render.py
  eval/      parser_metrics.py recourse_metrics.py run.py
```
