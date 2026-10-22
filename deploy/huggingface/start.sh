#!/bin/sh
# Запуск публичного демо: моки внешних сервисов внутри контейнера + API с фронтендом на порту 7860.
set -e

# Ключ подписи JWT: из секрета Space, а если его нет — случайный на время жизни контейнера
if [ -z "$JWT_SECRET" ]; then
  JWT_SECRET="$(/opt/api/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
  export JWT_SECRET
fi

cd /app/mocks
/opt/mocks/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090 --log-level warning &

cd /app/backend
exec /opt/api/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}" --proxy-headers --forwarded-allow-ips "*"
