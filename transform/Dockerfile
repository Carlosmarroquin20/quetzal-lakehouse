# Images are pinned by tag and digest. A tag can be moved to point at a
# different image; the digest cannot, so a build always starts from the
# image that was reviewed. Dependabot updates both together.
FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39

# uv installs exactly what uv.lock lists. Its version is pinned so the image
# builds the same way every time.
COPY --from=ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff /uv /usr/local/bin/uv

# The base image's pip is never used: uv installs everything. It carries its
# own copies of certifi, urllib3 and msgpack, which image scans report as
# vulnerable, so it is removed rather than kept up to date.
RUN pip uninstall --yes --quiet pip

WORKDIR /app
# No download cache: it would stay in the image as a second copy of every
# package.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PATH="/app/.venv/bin:$PATH"

# Dependencies go in their own layer, rebuilt only when the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# dbt writes its artifacts next to the project, so the directory has to belong
# to the user the job runs as. The scratch database goes in its own directory
# so that Compose can keep it in a volume between runs.
RUN useradd --create-home transform \
    && mkdir /app/state \
    && chown transform /app /app/state
USER transform
ENV DBT_DUCKDB_PATH=/app/state/quetzal.duckdb

# The DuckDB extensions and the dbt packages are downloaded here, at build
# time, so that a run does not depend on those downloads: httpfs reads S3,
# and aws finds credentials the standard AWS way when no key pair is given.
RUN python -c "import duckdb; c = duckdb.connect(); c.install_extension('httpfs'); c.install_extension('aws')"
COPY --chown=transform dbt_project.yml packages.yml package-lock.yml ./
RUN dbt deps

COPY --chown=transform profiles.yml ./
COPY --chown=transform plugins ./plugins
COPY --chown=transform models ./models
COPY --chown=transform seeds ./seeds
COPY --chown=transform tests ./tests

# Python runs as process 1 here, and Linux delivers no SIGTERM to process 1
# unless it handles it, so `docker stop` would wait ten seconds and kill it.
# Python does handle SIGINT, and stops in under a second. That matters when
# Airflow kills a task: it gives the task about ten seconds to stop and
# remove its container before killing it too.
STOPSIGNAL SIGINT
ENTRYPOINT ["dbt"]
CMD ["build"]
