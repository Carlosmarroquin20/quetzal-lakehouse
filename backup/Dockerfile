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

# pg_dump of the same major version as the catalog's Postgres (17); a dump
# taken with an older client than the server is refused.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# No download cache: it would stay in the image as a second copy of every
# package.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

# Dependencies go in their own layer, rebuilt only when the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# Debian already has a system user called backup.
RUN useradd --create-home catalog-backup
USER catalog-backup
ENV PATH="/app/.venv/bin:$PATH"

# Python runs as process 1 here, and Linux delivers no SIGTERM to process 1
# unless it handles it. Python does handle SIGINT, and stops in under a
# second.
STOPSIGNAL SIGINT
ENTRYPOINT ["python", "-m", "quetzal_backup"]
