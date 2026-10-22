"""Мультиязычность: перевод ответов API кабинета (EN/ZH) и понимание рассказа на EN/ZH."""
import re
from pathlib import Path

import pytest

from app import db as dbm
from app.domain.intake import parse
from app.domain.intake_lang import to_canonical
from app.i18n import tr
from app.services.pipeline import drain
from tests.conftest import login

CYR = re.compile("[А-Яа-яЁё]")
# Данные пользователя и реквизиты — не тексты интерфейса, их не переводим
DATA_KEYS = {"source", "filename", "purpose_comment", "collateral_description", "login", "full_name", "position",
             "director", "address", "okved_name", "region", "inn", "ogrn", "number", "account", "contract_number",
             "company", "content", "prefill", "name"}


def cyrillic_leaks(obj, path="") -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in DATA_KEYS and not (k == "name" and path.endswith("product")):
                continue
            out += cyrillic_leaks(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for v in obj:
            out += cyrillic_leaks(v, path + "[]")
    elif isinstance(obj, str) and CYR.search(obj):
        out.append(f"{path}: {obj[:80]}")
    return out


def test_catalog_patterns_translate_with_nested_parts():
    assert tr("Одобрено", "en") == "Approved"
    assert tr("Заявка 2610-00001 отправлена в банк", "zh") == "申请 2610-00001 已提交至银行"
    assert tr("Клиент принял условия: Ваши условия", "en") == "Client accepted the terms: Your terms"
    assert tr("Сумма должна быть от 100 000 до 5 000 000 ₽", "en") == "The amount must be between ₽100 000 and ₽5 000 000"
    assert tr("ООО «Колосок»", "en") == "ООО «Колосок»"  # неизвестная строка остаётся как есть


@pytest.mark.parametrize("text, expected", [
    ("I need 2 million for a new oven, will repay in 3 years, revenue around 600k a month",
     {"amount": 2_000_000, "term_months": 36, "purpose": "equipment", "monthly_revenue": 600_000}),
    ("We want to borrow 1.5 million to buy inventory for 6 months. Turnover is 7 million a year, I already pay 50k on a loan",
     {"amount": 1_500_000, "term_months": 6, "purpose": "working_capital", "monthly_revenue": 583_333, "existing_payments": 50_000}),
    ("需要200万买烤炉，3年还清，每月营业额60万，支出40万",
     {"amount": 2_000_000, "term_months": 36, "purpose": "equipment", "monthly_revenue": 600_000, "monthly_expenses": 400_000}),
    ("想贷一百五十万进货，期限半年，年营业额700万，现有贷款每月还5万，无抵押，比较急",
     {"amount": 1_500_000, "term_months": 6, "monthly_revenue": 583_333, "existing_payments": 50_000,
      "has_collateral": False, "urgency": "urgent"}),
    ("经营了7年，需要3百万采购原材料，分期2年", {"amount": 3_000_000, "term_months": 24, "business_age_months": 84}),
])
def test_story_in_english_and_chinese(text, expected):
    got = {i.field: i.value for i in parse(to_canonical(text)[0]).items}
    for key, value in expected.items():
        assert got.get(key) == value, (key, got)


@pytest.mark.parametrize("lang, greeting, status_word", [("en", "hello", "Application"), ("zh", "你好", "申请")])
def test_full_journey_has_no_untranslated_text(client, lang, greeting, status_word):
    tok = login(client, "kolosok")["Authorization"]
    h = {"Authorization": tok, "X-Lang": lang}
    leaks = []
    leaks += cyrillic_leaks(client.get("/api/catalog", headers=h).json(), "catalog")
    leaks += cyrillic_leaks(client.get("/api/feed", headers=h).json(), "feed")
    leaks += cyrillic_leaks(client.post("/api/precheck", headers=h, json={
        "product_code": "EXPRESS", "amount": 3_000_000, "term_months": 12, "business_age_months": 26,
        "monthly_revenue": 800_000, "monthly_expenses": 600_000, "tax_arrears": True}).json(), "precheck")
    a = client.post("/api/applications", headers=h, json={
        "product_code": "WORKING", "purpose": "working_capital", "amount": 3_000_000, "term_months": 24}).json()
    a = client.patch(f"/api/applications/{a['id']}", headers=h, json={
        "consents": {"bki": True, "personal_data": True},
        "form_data": {"monthly_revenue": 4_500_000, "monthly_expenses": 3_600_000, "existing_payments": 180_000}}).json()
    client.post(f"/api/applications/{a['id']}/submit", headers=h, json={})
    with dbm.SessionLocal() as s:
        drain(s, a["id"])
    a = client.get(f"/api/applications/{a['id']}", headers=h).json()
    assert a["status"] == "APPROVED"
    leaks += cyrillic_leaks(a, "application")
    chat = client.post("/api/assistant/chat", headers=h, json={"message": greeting}).json()
    assert not CYR.search(chat["content"].replace("Пётр", ""))
    status = client.post("/api/assistant/chat", headers=h, json={
        "message": "status?" if lang == "en" else "我的申请进度？"}).json()
    assert status_word in status["content"]
    leaks += cyrillic_leaks(client.get("/api/notifications", headers=h).json(), "notifications")
    err = client.post(f"/api/applications/{a['id']}/sign", headers=h, json={"code": "000000"})
    leaks += cyrillic_leaks(err.json(), "error")
    assert not leaks, leaks


def test_bank_console_stays_in_russian(client):
    uw = {**login(client, "underwriter"), "X-Lang": "en"}
    rows = client.get("/api/bank/applications", headers=uw).json()
    assert rows and all(CYR.search(r["status_label"]) for r in rows)


def test_intake_dialog_in_chinese(client):
    h = {**login(client, "flora"), "X-Lang": "zh"}
    r = client.post("/api/intake/message", headers=h, json={"message": "需要300万进货，1年还清，每月营业额80万"}).json()
    assert r["question"] == "monthly_expenses"
    assert "明白了" in r["reply"] and not CYR.search(r["reply"])
    ex = client.get("/api/intake/examples", headers=h).json()["examples"]
    assert all(re.search(r"[一-鿿]", e) for e in ex)


SAMPLES = Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_match_documents_and_steps_are_translated(client, lang):
    """Кредитный подбор, сравнение, проверка документов и шкала заявки — без русских строк."""
    h = {**login(client, "stroy"), "X-Lang": lang}
    leaks = []
    leaks += cyrillic_leaks(client.put("/api/match/profile", headers=h, json={"priority": "cost", "deferral": True}).json(), "match")
    client.post("/api/match/swipe", headers=h, json={"product_code": "WORKING", "action": "like"})
    client.post("/api/match/swipe", headers=h, json={"product_code": "OVERDRAFT", "action": "skip"})
    leaks += cyrillic_leaks(client.post("/api/match/swipe", headers=h, json={"product_code": "EXPRESS", "action": "like"}).json(), "swipe")
    leaks += cyrillic_leaks(client.get("/api/favorites", headers=h).json(), "favorites")
    leaks += cyrillic_leaks(client.get("/api/compare", headers=h).json(), "compare")
    for code in ("EXPRESS", "WORKING", "INVEST", "OVERDRAFT", "TENDER"):
        leaks += cyrillic_leaks(client.get(f"/api/offers/{code}", headers=h).json(), f"offer.{code}")
    leaks += cyrillic_leaks(client.get("/api/compare?codes=EXPRESS", headers=h).json(), "compare-error")

    a = client.post("/api/applications", headers=h, json={
        "product_code": "WORKING", "purpose": "working_capital", "amount": 15_000_000, "term_months": 36}).json()
    a = client.patch(f"/api/applications/{a['id']}", headers=h, json={
        "consents": {"bki": True, "personal_data": True},
        "form_data": {"monthly_revenue": 10_000_000, "monthly_expenses": 7_500_000, "existing_payments": 100_000}}).json()
    leaks += cyrillic_leaks(client.get(f"/api/applications/{a['id']}/checks", headers=h).json(), "checks.draft")
    for sample in ("vypiska_oshibka_chuzhaya_1c.txt", "vypiska_oshibka_2_mesyaca_1c.txt", "vypiska_oshibka_nizkie_oboroty_1c.txt"):
        client.post(f"/api/applications/{a['id']}/documents", headers=h, data={"doc_type": "bank_statement"},
                    files={"file": (sample, (SAMPLES / sample).read_bytes(), "text/plain")})
        leaks += cyrillic_leaks(client.get(f"/api/applications/{a['id']}/checks", headers=h).json(), f"checks.{sample}")
    fixed = client.post(f"/api/applications/{a['id']}/fix", headers=h, json={"field": "monthly_revenue", "value": 9_000_000}).json()
    leaks += cyrillic_leaks(fixed["checks"], "fix")
    a = client.get(f"/api/applications/{a['id']}", headers=h).json()
    client.post(f"/api/applications/{a['id']}/submit", headers=h, json={})
    with dbm.SessionLocal() as s:
        drain(s, a["id"])
    a = client.get(f"/api/applications/{a['id']}", headers=h).json()
    leaks += cyrillic_leaks({"steps": a["steps"], "tasks": a["tasks"], "alfik": a["alfik"], "timeline": a["timeline"]}, "app")
    leaks += cyrillic_leaks(client.get(f"/api/applications/{a['id']}/checks", headers=h).json(), "checks.scored")
    # без выписки для 15 млн банк сам попросит документ — задача клиенту на шкале
    b = client.post("/api/applications", headers=h, json={
        "product_code": "WORKING", "purpose": "working_capital", "amount": 15_000_000, "term_months": 36}).json()
    b = client.patch(f"/api/applications/{b['id']}", headers=h, json={
        "consents": {"bki": True, "personal_data": True},
        "form_data": {"monthly_revenue": 10_000_000, "monthly_expenses": 7_500_000, "existing_payments": 520_000}}).json()
    client.post(f"/api/applications/{b['id']}/submit", headers=h, json={})
    with dbm.SessionLocal() as s:
        drain(s, b["id"])
    b = client.get(f"/api/applications/{b['id']}", headers=h).json()
    assert b["status"] == "INFO_REQUESTED" and b["tasks"]
    leaks += cyrillic_leaks({"steps": b["steps"], "tasks": b["tasks"], "alfik": b["alfik"]}, "info")
    applied = client.post("/api/offers/EXPRESS/apply", headers=h, json={}).json()
    leaks += cyrillic_leaks({"steps": applied["steps"], "tasks": applied["tasks"], "timeline": applied["timeline"]}, "applied")
    assert not leaks, leaks
