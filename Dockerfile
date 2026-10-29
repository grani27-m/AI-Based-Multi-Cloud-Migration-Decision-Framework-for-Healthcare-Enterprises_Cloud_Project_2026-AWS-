# syntax=docker/dockerfile:1
# ---- stage 1: build the React dashboard ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
# optional corporate/sandbox CA: docker build --secret id=ca,src=/path/ca.crt (no-op when absent)
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca; fi; npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- stage 2: API (serves the built dashboard on the same port) ----
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY requirements.txt ./
RUN --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY src ./src
COPY data_ingestion ./data_ingestion
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
COPY models ./models
COPY results/model ./results/model
COPY dataset/config ./dataset/config
COPY dataset/metadata ./dataset/metadata
COPY dataset/samples ./dataset/samples
COPY infra/aws/service_status.json ./infra/aws/service_status.json
COPY --from=web /web/dist ./frontend/dist
RUN mkdir -p /app/runtime && chown -R app:app /app/runtime
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
CMD ["uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
