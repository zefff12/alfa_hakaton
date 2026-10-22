"""Диалог «Расскажите Альфику»: из рассказа клиента — в готовый черновик заявки.

Состояние диалога хранится на клиенте и передаётся в каждом запросе (сервер
stateless), черновик создаётся одним действием после подтверждения клиентом.
"""
import json
import logging
import re

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import advisor, calculator, readiness
from app.domain.intake import FIELD_LABELS, MONEY_FIELDS, Extracted, display, normalize, parse
from app.domain.intake_lang import to_canonical
from app.i18n import L, tr
from app.domain.products import PRODUCTS, PURPOSES, get_product
from app.domain.state_machine import Actor
from app.models import Application, User
from app.services import pipeline
from app.services.applications import next_number

log = logging.getLogger("intake")

REQUIRED = ("amount", "purpose", "term_months", "monthly_revenue", "monthly_expenses")

def question(field: str) -> str:
    return {
        "amount": L("Сколько денег нужно? Можно примерно: «около 2 млн».",
                    "How much money do you need? A rough figure is fine: “about 2 million”.",
                    "需要多少资金？说个大概就行，比如“200万左右”。"),
        "purpose": L("На что пойдут деньги? Например: закупка товара, оборудование, ремонт, кассовый разрыв, госконтракт.",
                     "What is the money for? For example: stock, equipment, renovation, a cash gap, a government contract.",
                     "资金用途是什么？例如：进货、设备、装修、资金缺口、政府合同。"),
        "term_months": L("За какой срок комфортно вернуть? Например: «за 2 года» или «на 18 месяцев».",
                         "Over what period can you comfortably repay? For example: “in 2 years” or “over 18 months”.",
                         "多长时间还清比较轻松？例如：“2年还清”或“分期18个月”。"),
        "monthly_revenue": L("Какая у бизнеса выручка в месяц — в среднем за последние полгода?",
                             "What is the business's monthly revenue — on average over the last six months?",
                             "企业每月营业额是多少？按最近半年的平均值即可。"),
        "monthly_expenses": L("А сколько в месяц уходит на расходы: аренда, зарплаты, закупки, налоги?",
                              "And how much goes on expenses each month: rent, salaries, purchases, taxes?",
                              "每月支出大概多少？包括房租、工资、采购、税费。"),
        "existing_payments": L("Есть ли сейчас другие кредиты или лизинг? Если да — сколько платите в месяц.",
                               "Do you have other loans or leases now? If so, how much do you pay per month?",
                               "目前还有其他贷款或租赁吗？如果有，每月还多少？"),
        "has_collateral": L("Есть ли залог? Для оборудования залогом может стать сама покупка.",
                            "Do you have collateral? For equipment, the purchase itself can serve as collateral.",
                            "有抵押物吗？购买设备时，设备本身就可以作为抵押。"),
    }[field]


def examples() -> list[str]:
    return {
        "en": ["I need 2 million for a new oven, will repay in 3 years, revenue around 4.5 million a month, expenses 3.6 million",
               "We want to borrow 1.5 million to buy stock for 6 months, turnover is 7 million a year",
               "We won a tender, need 5 million to fulfil the contract over 9 months, revenue 3.5 million a month"],
        "zh": ["需要200万买新烤炉，3年还清，每月营业额450万左右，支出360万",
               "想贷150万进货，期限半年，年营业额700万",
               "中标了政府合同，需要500万，9个月还清，每月流水350万"],
    }.get(L("ru", "en", "zh"), [
        "Нужно 2 млн на новую печь, верну за 3 года, выручка около 600 тысяч в месяц, расходы 400 тысяч",
        "Хочу взять полтора миллиона на закупку товара к Новому году на полгода, оборот 7 млн в год",
        "Выиграли тендер, нужно 5 млн на исполнение контракта на 9 месяцев, выручка 3,5 млн в месяц",
    ])

LLM_PROMPT = """Извлеки из текста предпринимателя параметры кредита. Верни только JSON с ключами:
amount (рубли), term_months, purpose (одно из: {purposes}), monthly_revenue (рубли в месяц),
monthly_expenses (рубли в месяц), existing_payments (рубли в месяц), has_collateral (true/false).
Если значения нет в тексте — null. Не придумывай. Текст: «{text}»"""


def _llm_extract(text: str) -> list[Extracted]:
    s = get_settings()
    if not s.llm_enabled:
        return []
    try:
        r = httpx.post(f"{s.llm_url}/api/generate", timeout=s.llm_timeout_s, json={
            "model": s.llm_model, "stream": False, "format": "json", "options": {"temperature": 0},
            "prompt": LLM_PROMPT.format(purposes=", ".join(PURPOSES), text=text[:1500]),
        })
        r.raise_for_status()
        data = json.loads(r.json().get("response") or "{}")
    except Exception as exc:  # noqa: BLE001
        log.warning("llm_extract_failed error=%s", exc)
        return []
    items = []
    for key in ("amount", "term_months", "monthly_revenue", "monthly_expenses", "existing_payments"):
        v = data.get(key)
        if isinstance(v, (int, float)) and v > 0:
            if key == "term_months" and not 1 <= v <= 120:
                continue
            items.append(Extracted(key, int(v), "понято ИИ-моделью", 0.6, "llm"))
    if data.get("purpose") in PURPOSES:
        items.append(Extracted("purpose", data["purpose"], "понято ИИ-моделью", 0.6, "llm"))
    if isinstance(data.get("has_collateral"), bool):
        items.append(Extracted("has_collateral", data["has_collateral"], "понято ИИ-моделью", 0.6, "llm"))
    return items


def _contextual(text: str, asked: str | None, found: dict[str, Extracted], known: dict) -> None:
    """Короткий ответ на заданный вопрос: «около 900 тысяч», «2 года», «нет»."""
    if not asked:
        return
    t = normalize(text)
    if asked in MONEY_FIELDS and asked not in found:
        stray = found.get("amount")
        if stray and (asked != "amount") and ("amount" in known or not re.search(r"нужн|хочу|взять|кредит", t)):
            found.pop("amount")
            found[asked] = Extracted(asked, stray.value, stray.source)
    if asked == "term_months" and "term_months" not in found:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(год\w*|лет|месяц\w*|мес)", t)
        if m:
            n = float(m.group(1))
            found["term_months"] = Extracted("term_months", int(n * 12 if m.group(2)[0] in "гл" else n), m.group(0))
    if asked == "existing_payments" and "existing_payments" not in found and re.search(r"\bнет\b|не плачу|кредитов нет|нету|ничего", t):
        found["existing_payments"] = Extracted("existing_payments", 0, "кредитов нет")
    if asked == "has_collateral" and "has_collateral" not in found:
        if re.search(r"\bда\b|есть", t):
            found["has_collateral"] = Extracted("has_collateral", True, text[:60])
        elif re.search(r"\bнет\b|нету", t):
            found["has_collateral"] = Extracted("has_collateral", False, "без залога")


def _company_age(user: User) -> int | None:
    reg = user.company.registered_at if user.company else None
    return pipeline.business_age_months(reg) if reg else None


def step(user: User, message: str, state: dict | None) -> dict:
    state = state or {}
    known: dict = dict(state.get("fields") or {})
    asked = state.get("asked")

    canon, said_in = to_canonical(message)  # английский и китайский → канонический вид для парсера
    parsed = parse(canon)
    found = {i.field: i for i in parsed.items}
    _contextual(canon, asked, found, known)
    if said_in != "ru":
        for item in found.values():  # источник — исходная реплика клиента, а не служебная нормализация
            if item.via == "rules":
                item.source = message[:90]
    for item in _llm_extract(message):
        found.setdefault(item.field, item)

    newly = []
    for name, item in found.items():
        prev = known.get(name)
        if prev and prev.get("value") == item.value:
            continue  # то же значение — сохраняем исходную фразу
        newly.append(name)
        known[name] = item.to_dict()

    if "business_age_months" not in known and (age := _company_age(user)) is not None:
        known["business_age_months"] = {**Extracted("business_age_months", age, "по данным ЕГРЮЛ").to_dict(), "via": "egrul"}

    def val(name, default=None):
        return (known.get(name) or {}).get("value", default)

    recommendation = None
    if val("purpose") and val("amount"):
        need = advisor.NeedProfile(
            purpose=val("purpose"), amount=int(val("amount")), term_months=val("term_months"),
            business_age_months=int(val("business_age_months", 24)), has_collateral=bool(val("has_collateral", False)),
            urgency=val("urgency", "normal"), monthly_revenue=val("monthly_revenue"),
        )
        rec = advisor.recommend(need)
        best = get_product(rec["best"] or rec["items"][0]["product"]["code"])
        term = min(max(int(val("term_months") or best.min_term), best.min_term), best.max_term)
        amount = min(max(int(val("amount")), best.min_amount), best.max_amount)
        est = calculator.summary(amount, best.base_rate, term, best.revolving)
        recommendation = {"product_code": best.code, "product_name": best.name, "explanation": rec["explanation"],
                          "amount": amount, "term_months": term, "estimate": est,
                          "alternatives": [i["product"]["code"] for i in rec["items"][1:3] if i["fit_score"] >= 60]}
        if val("monthly_revenue") and val("monthly_expenses") is not None:
            pre = readiness.evaluate(readiness.PrecheckAnswers(
                product=best, amount=amount, term_months=term,
                business_age_months=int(val("business_age_months", 24)),
                monthly_revenue=float(val("monthly_revenue")), monthly_expenses=float(val("monthly_expenses")),
                existing_monthly_payments=float(val("existing_payments", 0) or 0),
                has_collateral=bool(val("has_collateral", False)),
                industry=(user.company.industry if user.company else None) or "other"))
            recommendation["readiness"] = {k: pre[k] for k in ("readiness", "level", "title", "suggestion", "tips", "blockers")}
        comfort = val("comfortable_payment")
        if comfort and not best.revolving and est["monthly_payment"] > comfort:
            longer = calculator.min_term_for_payment(amount, best.base_rate, comfort, best.max_term)
            c = display("comfortable_payment", comfort)
            recommendation["comfort_hint"] = (
                L(f"Чтобы платёж уложился в {c}, срок нужен от {longer} мес.",
                  f"To keep the payment within {c}, the term needs to be at least {longer} months.",
                  f"要让月供控制在{c}以内，期限至少需要{longer}个月。")
                if longer else
                L(f"Даже на {best.max_term} мес. платёж выше {c} — стоит уменьшить сумму.",
                  f"Even over {best.max_term} months the payment exceeds {c} — consider a smaller amount.",
                  f"即使分{best.max_term}个月，月供也超过{c}——建议降低金额。"))

    missing = [f for f in REQUIRED if f not in known]
    if not missing and "existing_payments" not in known and asked != "existing_payments":
        missing.append("existing_payments")
    if (not missing and recommendation and PRODUCTS[recommendation["product_code"]].collateral == "required"
            and "has_collateral" not in known):
        missing.append("has_collateral")
    next_q = missing[0] if missing else None

    def phrase(n: str) -> str:
        label, shown = tr(known[n]["label"]), tr(known[n]["display"])
        if L("ru", "en", "zh") != "zh":
            label = label.lower()
            shown = shown[0].lower() + shown[1:] if n == "purpose" else shown
        return f"{label}{L(': ', ': ', '：')}{shown}"

    understood = [phrase(n) for n in REQUIRED + tuple(FIELD_LABELS) if n in newly and n in known]
    understood = list(dict.fromkeys(understood))
    sep = L("; ", "; ", "；")
    if not parsed.items and not found:
        reply = L("Я не нашёл в сообщении цифр или цели 🤔 ", "I couldn't find any figures or a purpose in that 🤔 ",
                  "我没有在消息里找到金额或用途 🤔 ") + question(next_q or "amount")
    elif next_q:
        got = sep.join(understood)
        reply = (L(f"Понял — {got}. ", f"Got it — {got}. ", f"明白了——{got}。") if understood else "") + question(next_q)
    else:
        r = recommendation
        name, amount = tr(r["product_name"]), display("amount", r["amount"])
        term, pay = tr(display("term_months", r["term_months"])), display("amount", r["estimate"]["monthly_payment"])
        reply = L(f"Отлично, картина ясна! Под вашу задачу подходит «{name}»: {amount} на {term}, "
                  f"ориентировочный платёж {pay} в месяц.",
                  f"Great, the picture is clear! “{name}” fits your task: {amount} over {term}, "
                  f"estimated payment {pay} per month.",
                  f"很好，情况清楚了！最适合您的是“{name}”：{amount}，期限{term}，预计月供{pay}。")
        if r.get("readiness"):
            score = r["readiness"]["readiness"]
            reply += L(f" Предварительная готовность к подаче — {score} из 100.",
                       f" Preliminary readiness to apply: {score} out of 100.", f"初步申请准备度：{score}/100。")
        if r.get("comfort_hint"):
            reply += " " + r["comfort_hint"]
        reply += L(" Создать черновик заявки? Всё, что вы рассказали, я уже перенёс.",
                   " Shall I create an application draft? Everything you told me is already filled in.",
                   "要创建申请草稿吗？您说的内容我都已经填好了。")

    return {
        "state": {"fields": known, "asked": next_q, "turns": int(state.get("turns", 0)) + 1},
        "fields": [known[k] for k in FIELD_LABELS if k in known],
        "new_fields": newly,
        "missing": [{"field": f, "label": FIELD_LABELS[f]} for f in missing],
        "question": next_q,
        "reply": reply,
        "ready": not missing,
        "recommendation": recommendation,
        "llm_used": any(i.via == "llm" for i in found.values()),
    }


def create_application(db: Session, user: User, state: dict, product_code: str | None) -> Application:
    known = (state or {}).get("fields") or {}

    def val(name, default=None):
        return (known.get(name) or {}).get("value", default)

    product = get_product(product_code) or get_product("EXPRESS")
    purpose = val("purpose") if val("purpose") in product.purposes else product.purposes[0]
    amount = min(max(int(val("amount") or product.min_amount), product.min_amount), product.max_amount)
    term = min(max(int(val("term_months") or product.min_term), product.min_term), product.max_term)
    form = {k: val(k) for k in ("monthly_revenue", "monthly_expenses", "existing_payments") if val(k) is not None}
    app = Application(
        number=next_number(db), company_id=user.company_id, user_id=user.id, status="DRAFT",
        product_code=product.code, purpose=purpose, amount=amount, term_months=term,
        has_collateral=bool(val("has_collateral", False)), collateral_description=val("collateral_description"),
        purpose_comment="Со слов клиента в диалоге с Альфиком",
        form_data={**form, "source": "alfik_dialog",
                   "intake": [{"field": k, "value": v.get("value"), "source": v.get("source"), "via": v.get("via")}
                              for k, v in known.items()]},
        consents={}, requested_documents=[],
    )
    db.add(app)
    db.flush()
    pipeline.log_event(db, app, "CREATED", "Черновик заполнен Альфиком по рассказу клиента", actor=Actor.CLIENT,
                       actor_id=user.id, to_status="DRAFT", payload={"fields": list(known)})
    db.commit()
    return app
