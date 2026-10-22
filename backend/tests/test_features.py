"""Тесты «фишек»: заявка из рассказа, разбор выписки, резюме для андеррайтера."""
import pathlib

import pytest

from app import db as dbm
from app.domain import statement
from app.domain.intake import parse
from app.services.pipeline import drain
from tests.conftest import login

SAMPLES = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"


def values(text: str) -> dict:
    return {i.field: i.value for i in parse(text).items}


@pytest.mark.parametrize("text, expected", [
    ("Нужно 2 млн на новую печь, верну за 3 года, выручка около 600 тысяч в месяц",
     {"amount": 2_000_000, "term_months": 36, "purpose": "equipment", "monthly_revenue": 600_000}),
    ("хочу взять полтора миллиона на закупку товара на полгода. оборот 7 млн в год, расходы примерно 450 тыс в месяц, "
     "уже плачу 50 тысяч по кредиту",
     {"amount": 1_500_000, "term_months": 6, "purpose": "working_capital", "monthly_revenue": 583_333,
      "monthly_expenses": 450_000, "existing_payments": 50_000}),
    ("выиграли тендер на 12 млн, нужно 5 миллионов на исполнение контракта на 9 месяцев, выручка 3,5 млн в месяц, без залога",
     {"amount": 5_000_000, "term_months": 9, "purpose": "contract", "monthly_revenue": 3_500_000, "has_collateral": False}),
    ("кассовый разрыв, нужно тысяч 300 на зарплаты, бизнесу 2 года",
     {"amount": 300_000, "purpose": "cash_gap", "business_age_months": 24}),
])
def test_intake_parses_free_speech(text, expected):
    got = values(text)
    for key, value in expected.items():
        assert got.get(key) == value, (key, got)


def test_intake_does_not_confuse_years_and_terms():
    got = values("Работаем с 2019 года, нужно 800 000 рублей на ремонт, срочно. Платить могу не больше 60 тысяч")
    assert got["amount"] == 800_000
    assert got["comfortable_payment"] == 60_000
    assert got["urgency"] == "urgent"
    assert "term_months" not in got  # «с 2019 года» — не срок кредита
    assert got["business_age_months"] >= 12


def test_intake_dialog_creates_prefilled_draft(client):
    h = login(client, "kolosok")
    state = None
    for msg in ["Нужно 2 млн на новую печь, верну за 3 года, выручка около 600 тысяч в месяц",
                "примерно 420 тысяч", "нет", "да, сама печь"]:
        r = client.post("/api/intake/message", headers=h, json={"message": msg, "state": state}).json()
        state = r["state"]
    assert r["ready"] and r["recommendation"]["product_code"] == "INVEST"
    fields = state["fields"]
    assert fields["monthly_expenses"]["value"] == 420_000  # короткий ответ отнесён к заданному вопросу
    assert fields["existing_payments"]["value"] == 0
    assert fields["has_collateral"]["value"] is True
    assert fields["business_age_months"]["via"] == "egrul"
    app = client.post("/api/intake/create", headers=h, json={"state": state, "product_code": "INVEST"}).json()
    assert app["status"] == "DRAFT" and app["amount"] == 2_000_000 and app["term_months"] == 36
    assert app["form_data"]["monthly_expenses"] == 420_000 and app["has_collateral"]


def test_chat_offers_to_build_application_from_story(client):
    h = login(client, "flora")
    msg = client.post("/api/assistant/chat", headers=h, json={"message": "хочу взять 3 млн на закупку товара к 8 марта"}).json()
    action = msg["meta"]["actions"][0]
    assert action["to"] == "/talk" and "3 млн" in action["prefill"]


def test_statement_1c_and_csv_give_same_cleaned_turnover():
    a1 = statement.analyze(statement.parse((SAMPLES / "vypiska_kolosok_1c.txt").read_bytes(), "x.txt"), 4_500_000)
    a2 = statement.analyze(statement.parse((SAMPLES / "vypiska_kolosok.csv").read_bytes(), "x.csv"), 4_500_000)
    assert a1["format"] == "1c" and a2["format"] == "csv"
    assert a1["avg_monthly_inflow"] == a2["avg_monthly_inflow"]
    assert a1["excluded_total"] == 1_300_000  # перевод со своего счёта + займ учредителя
    assert a1["months_used"] == 6 and a1["confirms_declared"]


def test_statement_flags_customer_concentration_but_not_retail_acquiring():
    stroy = statement.analyze(statement.parse((SAMPLES / "vypiska_stroy_1c.txt").read_bytes(), "s.txt"))
    flora = statement.analyze(statement.parse((SAMPLES / "vypiska_flora_1c.txt").read_bytes(), "f.txt"))
    assert any("одного покупателя" in f for f in stroy["flags"])
    assert not any("одного покупателя" in f for f in flora["flags"])


def test_statement_rejects_unknown_format():
    with pytest.raises(statement.StatementError):
        statement.parse(b"%PDF-1.4 binary", "scan.pdf")


def test_statement_upload_drives_scoring_and_summary(client):
    """Завышенная выручка: выписка показывает меньше — банк считает по выписке, специалист видит резюме."""
    h = login(client, "stroy")
    app = client.post("/api/applications", headers=h, json={
        "product_code": "WORKING", "purpose": "working_capital", "amount": 15_000_000, "term_months": 36}).json()
    app = client.patch(f"/api/applications/{app['id']}", headers=h, json={
        "version": app["version"], "consents": {"bki": True, "personal_data": True},
        "form_data": {"monthly_revenue": 14_000_000, "monthly_expenses": 9_000_000, "existing_payments": 520_000}}).json()
    r = client.post(f"/api/applications/{app['id']}/documents", headers=h, data={"doc_type": "bank_statement"},
                    files={"file": ("vypiska.txt", (SAMPLES / "vypiska_stroy_1c.txt").read_bytes(), "text/plain")})
    assert r.status_code == 201
    app = r.json()
    assert app["statement"]["avg_monthly_inflow"] < 10_000_000
    assert any(e["event_type"] == "DOCUMENT_ANALYZED" for e in app["timeline"])
    client.post(f"/api/applications/{app['id']}/documents", headers=h, data={"doc_type": "tax_certificate"},
                files={"file": ("tax.pdf", b"%PDF tax", "application/pdf")})
    app = client.get(f"/api/applications/{app['id']}", headers=h).json()
    client.post(f"/api/applications/{app['id']}/submit", headers=h, json={"version": app["version"]})
    with dbm.SessionLocal() as s:
        drain(s, app["id"])

    uw = login(client, "underwriter")
    card = client.get(f"/api/bank/applications/{app['id']}", headers=uw).json()
    assert card["status"] == "MANUAL_REVIEW"
    assert card["scoring"]["input"]["monthly_revenue"] == card["statement"]["avg_monthly_inflow"]
    texts = " ".join(p["text"] for p in card["summary"]["points"])
    assert "Выписка" in texts and "одного покупателя" in texts
    assert card["summary"]["recommendation"] and card["summary"]["checks"]
    assert "summary" not in client.get(f"/api/applications/{app['id']}", headers=h).json()  # клиенту не раскрывается
