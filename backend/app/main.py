"""Точка входа API «Умный кредитный кабинет предпринимателя»."""
import asyncio
import contextlib
import json
import logging
import mimetypes
import os
import threading
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import text

from app import db as dbm
from app import i18n
from app.api import auth, bank, client
from app.config import get_settings
from app.db import Base
from app.seed import seed
from app.worker import worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")


def init_db() -> None:
    Base.metadata.create_all(dbm.engine)
    if get_settings().seed_demo_data:
        with dbm.SessionLocal() as session:
            seed(session)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    # Несколько реплик API могут стартовать одновременно — повторяем до готовности БД
    for attempt in range(30):
        try:
            init_db()
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("db_not_ready attempt=%s error=%s", attempt, exc)
            await asyncio.sleep(1)
    task = None
    if get_settings().run_worker_in_process:
        stop = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(worker_loop, stop))
    yield
    if task:
        stop.set()
        await task


app = FastAPI(
    title="Умный кредитный кабинет предпринимателя",
    version="1.0.0",
    description=(
        "Цифровой кредитный конвейер для малого и микробизнеса: кабинет клиента с ассистентом Альфиком, "
        "автоматическая обработка заявки (проверка → ЕГРЮЛ/ФНС/БКИ → скоринг → решение) и консоль андеррайтера. "
        "Все данные синтетические, внешние сервисы — локальные моки."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Сквозной идентификатор запроса и журнал доступа — для трассировки в логах."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        log.exception("unhandled request_id=%s path=%s", request_id, request.url.path)
        response = JSONResponse({"detail": "Внутренняя ошибка сервиса", "request_id": request_id}, status_code=500)
    response.headers["X-Request-ID"] = request_id
    if request.url.path.startswith("/api"):
        log.info("request id=%s %s %s -> %s %.0fms", request_id, request.method, request.url.path,
                 response.status_code, (time.perf_counter() - started) * 1000)
    return response


@app.middleware("http")
async def i18n_layer(request: Request, call_next):
    """Язык кабинета клиента: X-Lang / Accept-Language → перевод JSON-ответа по каталогу.

    Консоль банка (/api/bank) — внутренний инструмент, остаётся на русском.
    """
    lang = i18n.parse_lang(request.headers.get("x-lang"), request.headers.get("accept-language"))
    token = i18n.set_lang(lang)
    try:
        response = await call_next(request)
    finally:
        i18n.reset_lang(token)
    path = request.url.path
    if (lang == "ru" or not path.startswith("/api") or path.startswith("/api/bank")
            or "application/json" not in response.headers.get("content-type", "")):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-length", "content-type")}
    try:
        data = i18n.localize(json.loads(body), lang)
    except ValueError:
        return Response(body, status_code=response.status_code, headers=headers, media_type="application/json")
    return JSONResponse(data, status_code=response.status_code, headers={**headers, "Content-Language": lang})


@app.get("/health/live", tags=["Служебные"], summary="Liveness-проба")
def live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["Служебные"], summary="Readiness-проба (БД доступна)")
def ready():
    try:
        with dbm.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "db": str(exc)[:200]}, status_code=503)
    return {"status": "ok", "db": "ok"}


app.include_router(auth.router)
app.include_router(client.router)
app.include_router(bank.router)

STATIC_DIR = get_settings().static_dir
if STATIC_DIR:
    # Публичное демо одним контейнером: те же файлы, что раздаёт nginx в docker compose.
    # Неизвестный путь отдаёт index.html — маршрутизацию страниц делает React Router.
    root = os.path.realpath(STATIC_DIR)
    # в slim-образах системный список типов неполный
    for ext, mime in ((".webp", "image/webp"), (".woff2", "font/woff2"), (".js", "text/javascript")):
        mimetypes.add_type(mime, ext)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith(("api/", "health/")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        file = os.path.realpath(os.path.join(root, path))
        if path and file.startswith(root + os.sep) and os.path.isfile(file):
            cache = "public, max-age=2592000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(file, headers={"Cache-Control": cache})
        return FileResponse(os.path.join(root, "index.html"), headers={"Cache-Control": "no-cache"})
