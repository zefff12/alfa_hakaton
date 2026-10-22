# Публичное демо на Hugging Face Spaces: весь кабинет в одном контейнере.
# Space содержит только этот Dockerfile и README.md; код берётся из публичного GitHub-репозитория.
# Отличия от docker compose: SQLite вместо PostgreSQL (демо-данные создаются заново при каждом
# запуске), обработчик заявок работает внутри API, фронтенд раздаёт сам API (STATIC_DIR).

FROM alpine:3.20 AS src
RUN apk add --no-cache git
ARG REPO=https://github.com/zefff12/alfa_hakaton.git
ARG REF=main
# Ответ GitHub меняется с каждым коммитом — кеш сборки сбрасывается, и в Space попадает свежий код
ADD https://api.github.com/repos/zefff12/alfa_hakaton/commits/main /tmp/latest-commit.json
RUN git clone --depth 1 --branch "$REF" "$REPO" /src

FROM node:22-alpine AS web
WORKDIR /web
COPY --from=src /src/frontend/package.json /src/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY --from=src /src/frontend ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.11.14

COPY --from=src /src/backend /app/backend
COPY --from=src /src/mocks /app/mocks
COPY --from=src /src/deploy/huggingface/start.sh /app/start.sh
RUN cd /app/backend && UV_PROJECT_ENVIRONMENT=/opt/api uv sync --frozen --no-dev --no-install-project \
 && cd /app/mocks && UV_PROJECT_ENVIRONMENT=/opt/mocks uv sync --frozen --no-dev --no-install-project
COPY --from=web /web/dist /app/static

# Spaces запускает контейнер от пользователя с UID 1000
RUN useradd --create-home --uid 1000 user && mkdir -p /data/storage && chown -R user /data /app
USER user

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
CMD ["sh", "/app/start.sh"]
