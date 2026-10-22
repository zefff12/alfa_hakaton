# Публичное демо одним контейнером (Render и любой хостинг Docker).
# Полная инфраструктура — docker-compose.yml; здесь всё нужное для показа в одном образе:
# API с обработчиком заявок, моки ЕГРЮЛ/ФНС/БКИ и собранный фронтенд (его отдаёт сам API).
# База — SQLite: демо-данные создаются заново при каждом запуске.
#   docker build -t alfa-demo . && docker run -p 7860:7860 alfa-demo   → http://localhost:7860

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.11.14

COPY backend/pyproject.toml backend/uv.lock /app/backend/
COPY mocks/pyproject.toml mocks/uv.lock /app/mocks/
RUN cd /app/backend && UV_PROJECT_ENVIRONMENT=/opt/api uv sync --frozen --no-dev --no-install-project \
 && cd /app/mocks && UV_PROJECT_ENVIRONMENT=/opt/mocks uv sync --frozen --no-dev --no-install-project
COPY backend/app /app/backend/app
COPY mocks/app /app/mocks/app
COPY deploy/start.sh /app/start.sh
COPY --from=web /web/dist /app/static

RUN useradd --create-home --uid 1000 appuser && mkdir -p /data/storage && chown -R appuser /data /app
USER appuser

ENV DATABASE_URL=sqlite:////data/credit.db \
    STORAGE_DIR=/data/storage \
    STATIC_DIR=/app/static \
    RUN_WORKER_IN_PROCESS=true \
    EGRUL_URL=http://127.0.0.1:8090/egrul \
    FNS_URL=http://127.0.0.1:8090/fns \
    BKI_URL=http://127.0.0.1:8090/bki \
    MOCK_LATENCY_MS=300 \
    ENVIRONMENT=demo

EXPOSE 7860
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=5 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"7860\")}/health/live').status==200 else 1)"
CMD ["sh", "/app/start.sh"]
