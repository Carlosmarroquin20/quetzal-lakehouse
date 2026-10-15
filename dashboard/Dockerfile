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
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home dashboard
USER dashboard

# The DuckDB extension that reads S3 is downloaded here, at build time, so
# that starting the dashboard does not depend on that download.
RUN python -c "import duckdb; duckdb.connect().install_extension('httpfs')"

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
