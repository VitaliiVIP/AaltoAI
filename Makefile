# AaltoAI — hiring pre-screener with algorithmic recourse.
#
#   make setup     install everything
#   make dev       run the app (backend :8000 + frontend :5173)
#
# `make help` lists everything else.

BACKEND_PORT  ?= 8000
FRONTEND_PORT ?= 5173

UV  ?= uv
NPM ?= npm

# `dev` needs `wait -n` (bash-only — plain `wait` blocks for *all* background
# jobs, so if one dies immediately the recipe hangs on the other forever
# instead of cleaning up). /bin/sh here is dash, which doesn't have it.
SHELL := bash

BACKEND  := backend
FRONTEND := frontend
CVS      := $(FRONTEND)/public/assets/cvs
CV_TEXT  := $(BACKEND)/data/cv_text

.DEFAULT_GOAL := help
.PHONY: help setup setup-backend setup-frontend dev backend frontend \
        check-ports check-backend-port check-frontend-port \
        test typecheck build preview check extract add-cv eval pool audit clean

help: ## Show this help
	@echo "AaltoAI — hiring pre-screener with algorithmic recourse"
	@echo
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  Ports: BACKEND_PORT=$(BACKEND_PORT) FRONTEND_PORT=$(FRONTEND_PORT)"

# ---------------------------------------------------------------- setup ----

setup: setup-backend setup-frontend ## Install backend and frontend dependencies
	@echo
	@echo "Ready. Run 'make dev'."

setup-backend: $(BACKEND)/.env
	$(UV) sync --project $(BACKEND)

setup-frontend: $(FRONTEND)/node_modules

$(FRONTEND)/node_modules: $(FRONTEND)/package-lock.json
	@command -v $(NPM) >/dev/null 2>&1 || { \
		echo "npm not found on PATH. With nvm, run 'nvm use' first; otherwise install"; \
		echo "Node.js (which bundles npm) from https://nodejs.org or your package manager."; \
		exit 127; }
	cd $(FRONTEND) && $(NPM) install --no-audit --no-fund
	@touch $(FRONTEND)/node_modules

$(BACKEND)/.env:
	@cp $(BACKEND)/.env.example $@
	@echo "Created $@ — put your ANTHROPIC_API_KEY in it."
	@echo "(Only 'Polish with Claude' and CV upload need it; everything else"
	@echo " runs on the deterministic templates.)"

# ------------------------------------------------------------------ run ----

# uvicorn and Vite both die with a raw traceback when their port is taken, and
# under `make dev` that arrives interleaved with the other server's startup
# noise. Look first and say what is actually going on. $(1) port, $(2) what it
# is for.
define check_port
port=$(1); who="$(2)"; pid=""; busy=""; \
if command -v lsof >/dev/null 2>&1; then \
	pid=$$(lsof -ti tcp:$$port -sTCP:LISTEN 2>/dev/null | head -1); \
	[ -n "$$pid" ] && busy=yes; \
elif command -v ss >/dev/null 2>&1; then \
	line=$$(ss -ltnpH "sport = :$$port" 2>/dev/null | head -1); \
	[ -n "$$line" ] && busy=yes; \
	pid=$$(printf '%s\n' "$$line" | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2); \
fi; \
if [ -n "$$busy" ]; then \
	kill_hint=""; \
	[ -n "$$pid" ] && kill_hint=", or: kill $$pid"; \
	echo; \
	echo "Port $$port is already in use, so the $$who cannot start."; \
	[ -n "$$pid" ] && echo "  pid $$pid is $$(ps -p $$pid -o args= 2>/dev/null | cut -c1-72)"; \
	echo "  Usually this is a 'make dev' still running in another terminal."; \
	echo; \
	echo "  Stop it there with Ctrl-C$$kill_hint"; \
	echo "  Or use free ports:  make dev BACKEND_PORT=8001 FRONTEND_PORT=5174"; \
	echo; \
	exit 1; \
fi
endef

check-ports: check-backend-port check-frontend-port ## Check that the dev ports are free

check-backend-port:
	@$(call check_port,$(BACKEND_PORT),backend API)

check-frontend-port:
	@$(call check_port,$(FRONTEND_PORT),Vite dev server)

dev: $(FRONTEND)/node_modules check-ports ## Run backend and frontend together (Ctrl-C stops both)
	@echo "backend  http://127.0.0.1:$(BACKEND_PORT)/   (API + throwaway demo page)"
	@echo "frontend http://127.0.0.1:$(FRONTEND_PORT)/  <- the app"
	@echo
	@trap 'kill 0 2>/dev/null; sleep 0.3; kill -9 0 2>/dev/null' INT TERM EXIT; \
	$(MAKE) --no-print-directory backend & \
	$(MAKE) --no-print-directory frontend & \
	wait -n

backend: check-backend-port ## Run only the API server (:8000)
	cd $(BACKEND) && $(UV) run uvicorn recourse_screen.api.app:app --reload --port $(BACKEND_PORT)

frontend: $(FRONTEND)/node_modules check-frontend-port ## Run only the Vite dev server (:5173)
	cd $(FRONTEND) && $(NPM) run dev -- --port $(FRONTEND_PORT) --strictPort

# ----------------------------------------------------------------- check ----

test: ## Run the backend test suite (deterministic, no LLM calls)
	cd $(BACKEND) && $(UV) run pytest -q

typecheck: $(FRONTEND)/node_modules ## Type-check the frontend
	cd $(FRONTEND) && $(NPM) exec -- tsc -b

build: $(FRONTEND)/node_modules ## Production build of the frontend into frontend/dist/
	cd $(FRONTEND) && $(NPM) run build

preview: build ## Serve the production build
	cd $(FRONTEND) && $(NPM) run preview

check: test typecheck build ## Everything CI would run

# ------------------------------------------------------------------ data ----

extract: ## LLM-extract any new CVs in backend/data/cv_text (cached by content hash)
	cd $(BACKEND) && $(UV) run python scripts/extract_demo_cvs.py

# Normalises the filename, because candidate_id is the file stem and the UI
# reconstructs the display name from it.
add-cv: ## Add a CV to the pool: make add-cv PDF=path/to/cv.pdf
	@test -n "$(PDF)" || { echo "usage: make add-cv PDF=path/to/cv.pdf"; exit 1; }
	@test -f "$(PDF)" || { echo "no such file: $(PDF)"; exit 1; }
	@stem=$$(basename "$(PDF)" .pdf | tr 'A-Z ' 'a-z_' | tr -cd 'a-z0-9_-'); \
	echo "adding $$stem"; \
	cp "$(PDF)" "$(CVS)/$$stem.pdf"; \
	pdftotext -layout "$(CVS)/$$stem.pdf" "$(CV_TEXT)/$$stem.txt"; \
	pdftoppm -png -r 100 -f 1 -l 1 "$(CVS)/$$stem.pdf" "$(CVS)/$$stem"; \
	mv -f "$(CVS)/$$stem-1.png" "$(CVS)/$$stem.png" 2>/dev/null || true
	@$(MAKE) --no-print-directory extract
	@echo "Added. Note this grows the mode-B pool and shifts every rank."

eval: ## Synthetic corpus + parser/recourse metrics (costs LLM calls)
	cd $(BACKEND) && $(UV) run python scripts/run_eval.py --n 30

pool: ## Print the scored candidate pool without starting anything
	@cd $(BACKEND) && $(UV) run python -c "\
from recourse_screen import pipeline; \
from recourse_screen.loaders import load_job, manifest_for_job; \
from recourse_screen.recourse.ranking_mode import score_pool; \
from recourse_screen.score.scorer import max_score; \
j = load_job('data_scientist'); m = manifest_for_job(j); \
rows = sorted(score_pool(pipeline.load_pool(), j, m), key=lambda t: (not t[2], -t[1])); \
print(f'threshold {j.mode.A.threshold} of {max_score(j, m)}, top {j.mode.B.slots_N} in mode B'); \
[print(f'{i:3}. {s:4}  {\"ko-fail\" if not ko else \"\":8} {cid}') for i, (cid, s, ko) in enumerate(rows, 1)]"

audit: ## Verify the hash-chained decision log
	@cd $(BACKEND) && $(UV) run python -c "\
from recourse_screen.audit.log import verify_chain; \
ok, n, bad = verify_chain(); \
print(f'chain {\"verified\" if ok else \"BROKEN\"} - {n} records' + ('' if ok else f', first bad index {bad}'))"

# ----------------------------------------------------------------- clean ----

clean: ## Remove build output and caches (keeps deps, CVs and the profile cache)
	rm -rf $(FRONTEND)/dist $(FRONTEND)/node_modules/.tmp $(FRONTEND)/*.tsbuildinfo
	rm -rf $(BACKEND)/.pytest_cache
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} +
