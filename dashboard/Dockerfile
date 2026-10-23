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
    UV_NO_CACHE=1 \
    PATH="/app/.venv/bin:$PATH"

# Dependencies go in their own layer, rebuilt only when the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home dashboard
USER dashboard

# The DuckDB extensions are downloaded here, at build time, so that starting
# the dashboard does not depend on that download: httpfs reads S3, and aws
# finds credentials the standard AWS way when no key pair is given.
RUN python -c "import duckdb; c = duckdb.connect(); c.install_extension('httpfs'); c.install_extension('aws')"

COPY --chown=dashboard app.py ./
COPY --chown=dashboard views ./views

# No usage statistics. Naming the address the browser uses also keeps
# Streamlit from asking an outside service for the machine's public IP at
# start, to print it as a URL nobody should use. The code is baked into the
# image, so there are no files to watch for changes, and viewers get no
# developer menu.
EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.address=0.0.0.0", "--server.port=8501", \
    "--server.headless=true", "--server.fileWatcherType=none", \
    "--browser.gatherUsageStats=false", "--browser.serverAddress=localhost", \
    "--client.toolbarMode=viewer"]
