"""Сквозные сценарии кредитного конвейера через HTTP API (end-to-end на уровне бэкенда)."""
import io

from app import db as dbm
from app.services.pipeline import drain
from tests.conftest import login

CONSENTS = {"bki": True, "personal_data": True}


def run_pipeline(app_id: int) -> None:
    with dbm.SessionLocal() as s:
        drain(s, app_id)


def new_app(client, h, **params) -> dict:
    form = params.pop("form_data")
    r = client.post("/api/applications", json={k: params[k] for k in ("product_code", "purpose", "amount", "term_months")},
                    headers=h)
    assert r.status_code == 201, r.text
    app = r.json()
    r = client.patch(f"/api/applications/{app['id']}", json={
        "version": app["version"], "form_data": form, "consents": CONSENTS,
        "has_collateral": params.get("has_collateral", False)}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def submit_and_process(client, h, app: dict) -> dict:
    r = client.post(f"/api/applications/{app['id']}/submit", json={"version": app["version"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUBMITTED"
    run_pipeline(app["id"])
    return client.get(f"/api/applications/{app['id']}", headers=h).json()


def test_happy_path_approve_sign_disburse(client):
    h = login(client, "kolosok")
    app = new_app(client, h, product_code="WORKING", purpose="working_capital", amount=3_000_000, term_months=24,
                  form_data={"monthly_revenue": 4_500_000, "monthly_expenses": 3_600_000, "existing_payments": 180_000})
    app = submit_and_process(client, h, app)
    assert app["status"] == "APPROVED", app["decision"]
    statuses = [e["to_status"] for e in app["timeline"] if e["to_status"]]
    assert statuses[:6] == ["DRAFT", "SUBMITTED", "DATA_CHECK", "ENRICHMENT", "SCORING", "APPROVED"]
    assert app["company"]["okved"] == "10.71"  # реквизиты подтянуты из ЕГРЮЛ

    opt = app["offer"]["options"][0]
    r = client.post(f"/api/applications/{app['id']}/accept", json={"version": app["version"], "option_id": opt["id"]}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "SIGNING"
    app = r.json()
    r = client.post(f"/api/applications/{app['id']}/sign", json={"version": app["version"], "code": "000000"}, headers=h)
    assert r.status_code == 422  # неверный код
    r = client.post(f"/api/applications/{app['id']}/sign",
                    json={"version": app["version"], "code": app["signing"]["demo_code"]}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "ISSUING"
    run_pipeline(app["id"])
    app = client.get(f"/api/applications/{app['id']}", headers=h).json()
    assert app["status"] == "DISBURSED"
    assert len(app["loan"]["schedule"]) == 24
    assert "code_hash" not in (app["signing"] or {})


def test_counter_offer_for_young_business(client):
    h = login(client, "flora")
    app = new_app(client, h, product_code="EXPRESS", purpose="working_capital", amount=3_000_000, term_months=12,
                  form_data={"monthly_revenue": 800_000, "monthly_expenses": 600_000, "existing_payments": 15_000})
    app = submit_and_process(client, h, app)
    assert app["status"] == "COUNTER_OFFER"
    assert len(app["offer"]["options"]) >= 1
    assert "rules" not in app["decision"]  # клиенту не раскрываются внутренние правила


def test_info_request_then_underwriter(client):
    h = login(client, "stroy")
    app = new_app(client, h, product_code="WORKING", purpose="working_capital", amount=15_000_000, term_months=36,
                  form_data={"monthly_revenue": 10_000_000, "monthly_expenses": 7_500_000, "existing_payments": 520_000})
    # без выписки для суммы > 5 млн конвейер сам запросит документ на этапе проверки данных
    app = submit_and_process(client, h, app)
    assert app["status"] == "INFO_REQUESTED"
    assert {d["code"] for d in app["requested_documents"]} == {"bank_statement"}

    r = client.post(f"/api/applications/{app['id']}/resubmit", json={"version": app["version"]}, headers=h)
    assert r.status_code == 422  # документ ещё не загружен
    r = client.post(f"/api/applications/{app['id']}/documents", data={"doc_type": "bank_statement"},
                    files={"file": ("statement.pdf", io.BytesIO(b"%PDF-1.4 demo"), "application/pdf")}, headers=h)
    assert r.status_code == 201, r.text
    app = r.json()
    r = client.post(f"/api/applications/{app['id']}/resubmit", json={"version": app["version"]}, headers=h)
    assert r.status_code == 200
    run_pipeline(app["id"])
    app = client.get(f"/api/applications/{app['id']}", headers=h).json()
    # налоговый долг 64 тыс. → банк просит справку
    assert app["status"] == "INFO_REQUESTED"
    assert {d["code"] for d in app["requested_documents"]} == {"tax_certificate"}
    client.post(f"/api/applications/{app['id']}/documents", data={"doc_type": "tax_certificate"},
                files={"file": ("tax.pdf", io.BytesIO(b"%PDF tax"), "application/pdf")}, headers=h)
    app = client.get(f"/api/applications/{app['id']}", headers=h).json()
    client.post(f"/api/applications/{app['id']}/resubmit", json={"version": app["version"]}, headers=h)
    run_pipeline(app["id"])
    app = client.get(f"/api/applications/{app['id']}", headers=h).json()
    assert app["status"] == "MANUAL_REVIEW"  # 15 млн > лимита автоматического решения

    uw = login(client, "underwriter")
    queue = client.get("/api/bank/applications?queue=manual", headers=uw).json()
    assert any(row["id"] == app["id"] for row in queue)
    card = client.get(f"/api/bank/applications/{app['id']}", headers=uw).json()
    assert card["scoring"]["factors"] and card["enrichment"]["sources"]["bki"]
    r = client.post(f"/api/bank/applications/{app['id']}/decision", headers=uw, json={
        "version": card["version"], "outcome": "APPROVED", "amount": 12_000_000, "term_months": 36, "comment": "Лимит снижен"})
    assert r.status_code == 200, r.text
    app = client.get(f"/api/applications/{app['id']}", headers=h).json()
    assert app["status"] == "APPROVED"
    assert app["offer"]["options"][0]["amount"] == 12_000_000


def test_liquidating_company_rejected(client):
    h = login(client, "romashka")
    app = new_app(client, h, product_code="EXPRESS", purpose="other", amount=500_000, term_months=12,
                  form_data={"monthly_revenue": 300_000, "monthly_expenses": 200_000})
    app = submit_and_process(client, h, app)
    assert app["status"] == "REJECTED"
    assert "ликвидац" in app["decision"]["reasons"][0]["text"]


def test_bki_outage_goes_to_manual_review(client):
    h = login(client, "failover")
    app = new_app(client, h, product_code="EXPRESS", purpose="other", amount=500_000, term_months=12,
                  form_data={"monthly_revenue": 900_000, "monthly_expenses": 500_000})
    app = submit_and_process(client, h, app)
    assert app["status"] == "MANUAL_REVIEW"
    assert any(e["event_type"] == "INTEGRATION_ERROR" for e in app["timeline"])


def test_access_control_and_optimistic_lock(client):
    h = login(client, "kolosok")
    other = login(client, "flora")
    app = client.post("/api/applications", json={"product_code": "EXPRESS"}, headers=h).json()
    assert client.get(f"/api/applications/{app['id']}", headers=other).status_code == 404
    assert client.get("/api/bank/applications", headers=h).status_code == 403
    assert client.get("/api/applications").status_code == 401
    ok = client.patch(f"/api/applications/{app['id']}", json={"version": app["version"], "amount": 200_000}, headers=h)
    assert ok.status_code == 200
    stale = client.patch(f"/api/applications/{app['id']}", json={"version": app["version"], "amount": 300_000}, headers=h)
    assert stale.status_code == 409


def test_alfik_and_feed_personalization(client):
    h = login(client, "kolosok")
    msg = client.post("/api/assistant/chat", json={"message": "Какой статус моей заявки?"}, headers=h).json()
    assert msg["source"] == "rules" and "Заявка" in msg["content"]
    fallback = client.post("/api/assistant/chat", json={"message": "сколько звёзд на небе"}, headers=h).json()
    assert fallback["source"] == "fallback"

    feed_food = client.get("/api/feed", headers=h).json()
    feed_build = client.get("/api/feed", headers=login(client, "stroy")).json()
    assert feed_food["profile"]["industry"] == "food"
    assert [i["id"] for i in feed_food["items"]] != [i["id"] for i in feed_build["items"]]
    first = feed_food["items"][0]["id"]
    client.post("/api/feed/react", json={"item_id": first, "action": "hide"}, headers=h)
    assert first not in [i["id"] for i in client.get("/api/feed", headers=h).json()["items"]]


def test_precheck_and_calculator(client):
    h = login(client, "flora")
    r = client.post("/api/precheck", headers=h, json={
        "product_code": "EXPRESS", "amount": 3_000_000, "term_months": 12, "business_age_months": 26,
        "monthly_revenue": 800_000, "monthly_expenses": 600_000, "existing_monthly_payments": 15_000})
    assert r.status_code == 200
    assert r.json()["suggestion"]
    calc = client.post("/api/calculator", json={"product_code": "EXPRESS", "amount": 3_000_000, "term_months": 12,
                                                "comfortable_payment": 150_000}).json()
    assert calc["alternatives"] and all(a["monthly_payment"] <= 150_000 for a in calc["alternatives"])
