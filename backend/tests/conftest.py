import importlib.util
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TMP = pathlib.Path(os.environ.get("PYTEST_TMP", ROOT / ".pytest_tmp"))
TMP.mkdir(exist_ok=True)
DB_PATH = TMP / "test.db"
if DB_PATH.exists():
    DB_PATH.unlink()

os.environ.update({
    "DATABASE_URL": f"sqlite:///{DB_PATH.as_posix()}",
    "PIPELINE_STEP_DELAY_S": "0",
    "RUN_WORKER_IN_PROCESS": "false",
    "STORAGE_DIR": str(TMP / "storage"),
    "LLM_ENABLED": "false",
    "INTEGRATION_RETRIES": "1",
})

# Моки внешних сервисов подключаем напрямую (без сети), под отдельным именем модуля
_spec = importlib.util.spec_from_file_location("ext_mocks", ROOT.parent / "mocks" / "app" / "main.py")
ext_mocks = importlib.util.module_from_spec(_spec)
sys.modules["ext_mocks"] = ext_mocks
os.environ["MOCK_LATENCY_MS"] = "0"
_spec.loader.exec_module(ext_mocks)
ext_mocks.LATENCY_MS = 0


@pytest.fixture(autouse=True)
def fake_integrations(monkeypatch):
    from fastapi import HTTPException

    from app.integrations import clients

    def wrap(service, fn):
        def inner(*args):
            try:
                return fn(*args)
            except HTTPException as exc:
                raise clients.IntegrationError(service, f"HTTP {exc.status_code}")
        return inner

    monkeypatch.setattr(clients, "fetch_egrul", wrap("ЕГРЮЛ", lambda inn: ext_mocks.egrul(inn)))
    monkeypatch.setattr(clients, "fetch_fns", wrap("ФНС", lambda inn: ext_mocks.fns(inn)))
    monkeypatch.setattr(clients, "fetch_bki", wrap("БКИ", lambda inn, consent: ext_mocks.bki(
        ext_mocks.BkiRequest(inn=inn, consent_id=consent))))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, name: str) -> dict:
    r = client.post("/api/auth/login", json={"login": name, "password": "demo"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
