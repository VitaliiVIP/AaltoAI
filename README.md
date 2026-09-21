# AaltoAI

## Idea

An automated pre-screening system for hiring that explains to applicants what would need to change in their CV to get accepted. E.g., one more year of experience in some skill, or one more project on some topic, or knowledge of some framework. Technology is called "algorithmic recourse", can be coupled with the screening system itself, there are fancy technical solutions but not much actually made into a product.
## Running it

```bash
make setup     # backend deps (uv) + frontend deps (npm) + backend/.env
make dev       # backend :8000, frontend :5173 — open http://127.0.0.1:5173
```

`make help` lists the rest (`test`, `check`, `pool`, `audit`, `add-cv`, `extract`,
`cache-explanations`, `eval`).

The running app never calls a paid model. It is a long-term public demo, so everything the
model contributes is precomputed and committed under `backend/data/`: CV extractions in
`profiles/` and `profiles_raw/`, and the candidate-facing sentences in `explanations/`. A
decision the cache has not seen (an edited job, a restated CV) gets the deterministic template
text instead. `ANTHROPIC_API_KEY` in `backend/.env` is only needed for the scripts that refill
those caches (`make extract`, `make add-cv`, `make cache-explanations`, `make eval`); the API and
the UI have no path to the model at all.

## Deploying

Two images, published to GHCR by `.github/workflows/publish.yml` on every push to `main`:

- `recourse-web` — `frontend/Dockerfile`: Vite build served by nginx
- `recourse-api` — `backend/Dockerfile`: uvicorn on :8000, `backend/data` on a volume

They are wired up as `recourse.ilia.fi` in the separate `vps_deployment` repo
(`services/recourse/`), where Caddy terminates TLS and routes `/api/*` to the API with the
prefix stripped — the same rewrite `vite.config.ts` does in development, so no build-time API
base URL is involved. The site is public: nothing it serves spends a model call, and the CV pool
is synthetic.

## Documents

- `research/design_report.md` — proposed design, decision register, stack and build plan (start here)
- `research/algorithmic_recourse_and_counterfactual_explanations_in_hiring.md` — background: vendors, regulation, papers, critique
- `research/criteria_used_in_ai_hiring.md` — background: what employers actually configure
- `research/notes/` — technical briefs behind the design report (recourse engine, CV parsing and LLM use, ranking mode / gaming / evaluation) and a runnable CP-SAT toy solver
