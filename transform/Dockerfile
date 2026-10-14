FROM python:3.13-slim

# uv installs exactly what uv.lock lists. Its version is pinned so the image
# builds the same way every time.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Dependencies go in their own layer, rebuilt only when the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# dbt writes its artifacts and the scratch database next to the project, so
# the directory has to belong to the user the job runs as.
RUN useradd --create-home transform && chown transform /app
USER transform

# The DuckDB extension and the dbt packages are downloaded here, at build
# time, so that a run does not depend on those downloads.
RUN python -c "import duckdb; duckdb.connect().install_extension('httpfs')"
COPY --chown=transform dbt_project.yml packages.yml package-lock.yml ./
RUN dbt deps

COPY --chown=transform profiles.yml ./
COPY --chown=transform models ./models
COPY --chown=transform seeds ./seeds
COPY --chown=transform tests ./tests

ENTRYPOINT ["dbt"]
CMD ["build"]
