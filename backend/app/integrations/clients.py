"""Клиенты внешних сервисов с таймаутами, повторами и предохранителем (circuit breaker).

Сбой внешнего источника не должен ронять конвейер: при недоступности
сервиса заявка уходит на ручное рассмотрение с понятной причиной.
"""
import logging
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings

log = logging.getLogger("integrations")


class IntegrationError(Exception):
    def __init__(self, service: str, message: str):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.message = message


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_after_s: float = 30.0
    failures: int = 0
    opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at > self.reset_after_s:
            self.opened_at = None  # half-open: пробуем снова
            self.failures = 0
            return True
        return False

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()


_breakers: dict[str, CircuitBreaker] = {}


def _call(service: str, method: str, url: str, **kwargs) -> dict:
    s = get_settings()
    breaker = _breakers.setdefault(service, CircuitBreaker())
    if not breaker.allow():
        raise IntegrationError(service, "сервис временно отключён предохранителем")
    last_error = "неизвестная ошибка"
    for attempt in range(1, s.integration_retries + 1):
        try:
            with httpx.Client(timeout=s.integration_timeout_s) as client:
                resp = client.request(method, url, **kwargs)
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
            elif resp.status_code >= 400:
                breaker.success()
                raise IntegrationError(service, f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                breaker.success()
                return resp.json()
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
        log.warning("integration_retry service=%s attempt=%s error=%s", service, attempt, last_error)
        time.sleep(min(0.2 * 2 ** (attempt - 1), 1.0))
    breaker.failure()
    raise IntegrationError(service, f"нет ответа после {s.integration_retries} попыток ({last_error})")


def fetch_egrul(inn: str) -> dict:
    return _call("ЕГРЮЛ", "GET", f"{get_settings().egrul_url}/{inn}")


def fetch_fns(inn: str) -> dict:
    return _call("ФНС", "GET", f"{get_settings().fns_url}/{inn}")


def fetch_bki(inn: str, consent_id: str) -> dict:
    return _call("БКИ", "POST", f"{get_settings().bki_url}/report", json={"inn": inn, "consent_id": consent_id})
