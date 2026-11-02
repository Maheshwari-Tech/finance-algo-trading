# syntax=docker/dockerfile:1.7

# ---- 1. Frontend build ----
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python dependencies ----
FROM python:3.12-slim-bookworm AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /venv
COPY backend/requirements.txt /tmp/requirements.txt
RUN /venv/bin/pip install -r /tmp/requirements.txt

# ---- 3. Runtime ----
FROM python:3.12-slim-bookworm AS runtime
ARG GIT_SHA=dev
ENV PATH=/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    APP_VERSION=$GIT_SHA
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=deps /venv /venv
COPY backend/app ./backend/app
COPY config ./config
COPY examples ./examples
COPY --from=frontend /src/frontend/dist ./frontend/dist
USER app
WORKDIR /app/backend
EXPOSE 8123
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8123/api/ready', timeout=4).status == 200 else 1)"
# One worker per container keeps Prometheus counters exact; scale by running more containers.
# --forwarded-allow-ips='*' is safe because only Caddy can reach this port (it is not published).
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8123", \
     "--proxy-headers", "--forwarded-allow-ips=*", "--no-server-header", "--timeout-graceful-shutdown", "20"]
