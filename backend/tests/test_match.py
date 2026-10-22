"""«Кредитный подбор» (свайпы, избранное, сравнение) и проверка документов на несоответствия."""
from pathlib import Path

from app.domain.match import MatchProfile, build_deck
from tests.conftest import login

SAMPLES = Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"


def test_ranking_follows_client_priority_not_bank_profit():
    def first(priority: str) -> str:
        return build_deck(MatchProfile(purpose="working_capital", amount=3_000_000, term_months=24,
                                       priority=priority, business_age_months=60))["offers"][0]["code"]
    assert first("cost") == "WORKING"
    assert first("speed") == "EXPRESS"
    assert first("docs") == "EXPRESS"
    # неподходящий по цели продукт не может оказаться выше подходящих
    deck = build_deck(MatchProfile(purpose="working_capital", priority="cost", business_age_months=60))
    assert deck["offers"][-1]["code"] in {"INVEST", "TENDER"} and not deck["offers"][-1]["eligible"]


def test_swipes_refine_deck_and_fill_favorites(client):
    h = login(client, "kolosok")
    deck = client.put("/api/match/profile", headers=h, json={"priority": "balanced", "reset_swipes": True}).json()
    assert deck["configured"] and deck["stats"]["left"] == 5
    client.post("/api/match/swipe", headers=h, json={"product_code": "WORKING", "action": "like"})
    deck = client.post("/api/match/swipe", headers=h, json={"product_code": "OVERDRAFT", "action": "skip"}).json()
    assert deck["stats"] == {"total": 5, "liked": 1, "skipped": 1, "left": 3}
    assert {"WORKING", "OVERDRAFT"}.isdisjoint(o["code"] for o in deck["deck"])
    assert deck["insight"]  # после нескольких выборов система поясняет, что поняла
    assert deck["favorites"] == ["WORKING"]

    assert client.get("/api/compare", headers=h).status_code == 422  # одного варианта мало
    client.post("/api/favorites/EXPRESS", headers=h)
    cmp = client.get("/api/compare", headers=h).json()
    assert {c["code"] for c in cmp["columns"]} == {"WORKING", "EXPRESS"}
    assert cmp["best"]["speed"] == "EXPRESS" and len(cmp["rows"]) == 11
    favs = client.post("/api/favorites/EXPRESS/compare", headers=h).json()
    assert favs["compare_count"] == 1
    assert client.delete("/api/favorites", headers=h).json()["items"] == []


def test_offer_detail_and_apply_creates_draft(client):
    h = login(client, "flora")
    d = client.get("/api/offers/EXPRESS?amount=2000000&term=18", headers=h).json()
    assert d["offer"]["amount"] == 2_000_000 and d["offer"]["term_months"] == 18
    assert len(d["conditions"]) == 5 and d["documents"]
    app = client.post("/api/offers/EXPRESS/apply", headers=h, json={"amount": 2_000_000, "term_months": 18}).json()
    assert app["status"] == "DRAFT" and app["product_code"] == "EXPRESS" and app["amount"] == 2_000_000
    assert app["tasks"][0]["type"] == "submit" and app["steps"][0]["state"] == "active"
    assert client.get("/api/offers/NOPE", headers=h).status_code == 404


def _draft(client, h, revenue=4_500_000):
    a = client.post("/api/applications", headers=h, json={
        "product_code": "WORKING", "purpose": "working_capital", "amount": 3_000_000, "term_months": 24}).json()
    return client.patch(f"/api/applications/{a['id']}", headers=h, json={
        "version": a["version"], "form_data": {"monthly_revenue": revenue, "monthly_expenses": 3_000_000}}).json()


def _upload(client, h, app_id, sample):
    r = client.post(f"/api/applications/{app_id}/documents", headers=h, data={"doc_type": "bank_statement"},
                    files={"file": (sample, (SAMPLES / sample).read_bytes(), "text/plain")})
    assert r.status_code == 201, r.text
    return {c["code"]: c for c in client.get(f"/api/applications/{app_id}/checks", headers=h).json()["items"]}


def test_doc_check_finds_predefined_errors_and_fixes_form(client):
    h = login(client, "kolosok")
    a = _draft(client, h)
    checks = _upload(client, h, a["id"], "vypiska_oshibka_chuzhaya_1c.txt")
    assert checks["statement_owner"]["status"] == "error"
    assert {v["origin"] for v in checks["statement_owner"]["values"]} == {"Выписка 1С", "ЕГРЮЛ"}

    checks = _upload(client, h, a["id"], "vypiska_oshibka_2_mesyaca_1c.txt")
    assert checks["statement_period"]["status"] == "warn"

    checks = _upload(client, h, a["id"], "vypiska_oshibka_nizkie_oboroty_1c.txt")
    rev = checks["revenue_statement"]
    assert rev["status"] == "error" and rev["fix"]["field"] == "monthly_revenue"
    assert [v["origin"].split(" ")[0] for v in rev["values"]] == ["Анкета", "Выписка"]
    fixed = client.post(f"/api/applications/{a['id']}/fix", headers=h, json={"field": rev["fix"]["field"], "value": rev["fix"]["value"]}).json()
    assert fixed["application"]["form_data"]["monthly_revenue"] == rev["fix"]["value"]
    assert {c["code"]: c["status"] for c in fixed["checks"]["items"]}["revenue_statement"] == "ok"
    assert any(e["event_type"] == "FORM_FIXED" for e in fixed["application"]["timeline"])


def test_fix_is_blocked_after_submit_and_capacity_is_shown(client):
    h = login(client, "kolosok")
    a = _draft(client, h)
    client.patch(f"/api/applications/{a['id']}", headers=h, json={"consents": {"bki": True, "personal_data": True}})
    client.post(f"/api/applications/{a['id']}/submit", headers=h, json={})
    r = client.post(f"/api/applications/{a['id']}/fix", headers=h, json={"field": "monthly_revenue", "value": 1})
    assert r.status_code == 409
    cap = client.get("/api/me/capacity", headers=h).json()
    assert cap["amount"] and cap["source"] in {"fns", "scoring"}
