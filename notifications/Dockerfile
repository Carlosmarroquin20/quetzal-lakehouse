FROM python:3.13-slim

# uv installs exactly what uv.lock lists. Its version is pinned so the image
# builds the same way every time.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv

# The base image's pip is never used: uv installs everything. It carries its
# own copies of certifi, urllib3 and msgpack, which image scans report as
# vulnerable, so it is removed rather than kept up to date.
RUN pip uninstall --yes --quiet pip

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

RUN useradd --create-home notifications
USER notifications
ENV PATH="/app/.venv/bin:$PATH"

# The DuckDB extensions are downloaded here, at build time, so that a run
# does not depend on that download: httpfs reads S3, and aws finds
# credentials the standard AWS way when no key pair is given.
RUN python -c "import duckdb; c = duckdb.connect(); c.install_extension('httpfs'); c.install_extension('aws')"

ENTRYPOINT ["python", "-m", "quetzal_notifications"]
