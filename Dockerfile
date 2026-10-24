FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY cases ./cases
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" HOST=0.0.0.0 PORT=8000 POZHAN_LOG_DIR=/data/logs
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"

CMD ["pozhan", "serve"]
