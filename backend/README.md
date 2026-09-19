# Recourse pre-screener — backend

Demo backend for the AaltoAI hiring pre-screener with algorithmic recourse. Design:
`../research/design_report.md`. Decisions taken for this build are in the plan summary at the top of
that report's implementation (see git history) and in the module docstrings.

Pipeline: CV text → Claude structured extraction (LLM #1) → deterministic post-processing → enveloped
profile → knockouts ∧ additive scorer → CP-SAT minimum-cost recourse (k=3 diverse routes, flip-tested)
→ Claude one-sentence-per-delta verbalisation (LLM #2) → code-only checker → hash-chained audit log.

## Setup

```bash
cd backend
uv sync                       # Python 3.12+, installs ortools/anthropic/fastapi/...
cp .env.example .env          # put ANTHROPIC_API_KEY in .env
```

## Run

```bash
uv run pytest                                     # deterministic tests, no LLM calls
uv run python scripts/extract_demo_cvs.py         # LLM-extract data/cv_text/*.txt -> data/profiles/ (cached)
uv run uvicorn recourse_screen.api.app:app --reload   # http://localhost:8000/  (throwaway demo page)
uv run python scripts/run_eval.py --n 30          # synthetic corpus + parser/recourse metrics -> data/synth/eval_report.md
```

Add a CV: drop a PDF into `../frontend/public/assets/cvs/` and run
`pdftotext -layout file.pdf data/cv_text/file.txt`, then re-run the extraction script (only new files
call the API; profiles are cached by content hash).

## API (consumed by the React frontend in `../frontend/src`)

| Endpoint | Purpose |
|---|---|
| `GET /jobs` | Job templates with knockouts, weights, caps, costs, mode settings (the audit artefact) |
| `GET /candidates?job=&mode=A|B&N=` | Pool with score, knockouts, rank, decision, experience months and the two largest shortfalls. No LLM calls, no audit writes. |
| `POST /screen {candidate_id | cv_text, job_id, mode, N, explain}` | Full `ScreenResult`: profile with evidence, contributions, decision, routes, blockers, hints, explanation |
| `POST /extract` (multipart `file` or form `cv_text`) | Run LLM #1 only; caches the profile |
| `POST /restate {candidate_id, job_id, mode, N, confirmations:[{path,value}]}` | Candidate confirms missed fields; everything re-runs, new audit record linked to the parent |
| `GET /audit`, `GET /audit/{decision_id}` | Hash-chained records, chain verification |

The frontend (`npm run dev`, :5173) proxies `/api` here and defaults to `explain: false`, which
still returns a complete templated `Explanation` — the LLM verbaliser is only invoked from its
"Polish with Claude" button, so the whole UI works without an API key.

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
  restate.py audit/log.py pipeline.py api/app.py api/static/index.html
  synth/     sampler.py render.py
  eval/      parser_metrics.py recourse_metrics.py run.py
```
