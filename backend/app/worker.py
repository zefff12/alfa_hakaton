"""Воркер кредитного конвейера.

Забирает заявки, у которых наступило время следующего автоматического шага.
На PostgreSQL используется SELECT ... FOR UPDATE SKIP LOCKED, поэтому воркеров
можно масштабировать горизонтально без двойной обработки заявок.
"""
import logging
import signal
import threading
import time

from app import db as dbm
from app.config import get_settings
from app.services.pipeline import run_due

log = logging.getLogger("worker")


def worker_loop(stop: threading.Event | None = None) -> None:
    interval = get_settings().worker_poll_interval_s
    log.info("pipeline worker started, poll=%ss", interval)
    while not (stop and stop.is_set()):
        try:
            with dbm.SessionLocal() as session:
                processed = run_due(session)
            if processed:
                log.info("processed %s pipeline steps", processed)
        except Exception:  # noqa: BLE001
            log.exception("worker iteration failed")
        time.sleep(interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from app.main import init_db

    for attempt in range(30):
        try:
            init_db()
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("db_not_ready attempt=%s error=%s", attempt, exc)
            time.sleep(1)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker_loop(stop)


if __name__ == "__main__":
    main()
