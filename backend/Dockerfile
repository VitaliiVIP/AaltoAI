# API image. Build context is backend/ — see backend/.dockerignore, which keeps
# the 260 MB local .venv (and the dev audit log) out of the context entirely.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Links the GHCR package to the repo, so the package page shows its source and
# inherits the repo's access control.
LABEL org.opencontainers.image.source=https://github.com/VitaliiVIP/AaltoAI

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so an edit to the package doesn't re-resolve ortools.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY recourse_screen ./recourse_screen
RUN uv sync --frozen --no-dev

# data/ ships as a seed rather than as the live tree: the deploy mounts a volume
# at /app/data, which would otherwise hide the demo CVs and cached profiles baked
# into the image. The entrypoint copies it in without ever overwriting.
COPY data ./data-seed
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "recourse_screen.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
