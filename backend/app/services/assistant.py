"""Альфик — ассистент предпринимателя.

Гибридная архитектура:
1. Правила (intent-матчинг) отвечают на вопросы, где важна точность: статус заявки,
   причины решения, нужные документы, расчёт платежа. Работает всегда, без GPU.
2. Локальная open-weights LLM (Qwen2.5 через Ollama) — для свободных вопросов,
   если включена. Получает контекст клиента и жёсткие ограничения: не обещать
   одобрение, не выдумывать условия, отвечать по-русски и кратко.
"""
import logging
import re

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import calculator
from app.domain.products import PRODUCTS, get_product
from app.domain.state_machine import FINAL, LABELS, Status
from app.models import Application, ChatMessage, User
from app.services.alfik_texts import STAGES

log = logging.getLogger("assistant")

SYSTEM_PROMPT = """Ты — Альфик, дружелюбный помощник предпринимателя в кредитном кабинете банка.
Правила:
- Отвечай по-русски, коротко (до 5 предложений), простыми словами, без банковского жаргона.
- Никогда не обещай одобрение кредита и не называй условия, которых нет в контексте.
- Если вопрос про конкретную заявку — опирайся только на данные контекста.
- Не проси паспортные данные, пароли, номера карт.
- Если не знаешь ответа — честно скажи и предложи обратиться к специалисту через чат кабинета.
Каталог продуктов (условия демонстрационные):
{catalog}
Контекст клиента:
{context}"""

FORBIDDEN = re.compile(r"(гарантир\w*|100\s*%|точно одобр\w*)", re.IGNORECASE)


def _money(v) -> str:
    return f"{float(v):,.0f} ₽".replace(",", " ")


def _active_application(db: Session, user: User, application_id: int | None) -> Application | None:
    if application_id:
        app = db.get(Application, application_id)
        if app and app.company_id == user.company_id:
            return app
    apps = db.scalars(
        select(Application).where(Application.company_id == user.company_id).order_by(Application.updated_at.desc())
    ).all()
    active = [a for a in apps if Status(a.status) not in FINAL]
    return (active or apps or [None])[0]


def _catalog() -> str:
    return "\n".join(
        f"- {p.name}: {p.min_amount:,}–{p.max_amount:,} ₽, {p.min_term}–{p.max_term} мес., от {p.base_rate:g}%, "
        f"залог: {dict(none='не нужен', optional='по желанию', required='обязателен')[p.collateral]}".replace(",", " ")
        for p in PRODUCTS.values()
    )


def _context(user: User, app: Application | None) -> str:
    lines = [f"Клиент: {user.full_name}, компания: {user.company.name if user.company else '—'}"]
    if user.company and user.company.okved_name:
        lines.append(f"Деятельность: {user.company.okved_name}")
    if app:
        p = get_product(app.product_code)
        lines.append(f"Заявка {app.number}: статус «{LABELS[Status(app.status)]}», продукт: {p.name if p else 'не выбран'}, "
                     f"сумма: {_money(app.amount or 0)}, срок: {app.term_months or '—'} мес.")
        if app.decision and app.decision.get("reasons"):
            lines.append("Причины решения: " + "; ".join(r["text"] for r in app.decision["reasons"]))
        if app.requested_documents:
            lines.append("Запрошенные документы: " + ", ".join(app.requested_documents))
    else:
        lines.append("Заявок пока нет")
    return "\n".join(lines)


# --- Правила -----------------------------------------------------------------

def _a(label: str, to: str) -> dict:
    return {"label": label, "to": to}


def rule_answer(text: str, user: User, app: Application | None) -> dict | None:
    t = text.lower().replace("ё", "е")

    def has(*patterns: str) -> bool:
        return any(re.search(p, t) for p in patterns)

    if has(r"^(привет|здравств|добр\w+ (день|утро|вечер)|хай|hello)"):
        name = user.full_name.split()[1] if len(user.full_name.split()) > 1 else user.full_name
        return {"text": f"Привет, {name}! Я Альфик. Помогу выбрать кредит, оценить шансы, заполнить заявку и подскажу, "
                        f"что происходит на каждом этапе. С чего начнём?",
                "actions": [_a("Подобрать кредит", "/advisor"), _a("Узнать шансы", "/precheck")]}

    if has(r"платеж\w* (слишком |очень )?(больш|высок)", r"дорого", r"снизить платеж", r"уменьшить платеж"):
        if app and app.amount and app.term_months and get_product(app.product_code):
            p = get_product(app.product_code)
            longer = min(p.max_term, (app.term_months or 12) * 2)
            now = calculator.summary(app.amount, p.base_rate, app.term_months, p.revolving)["monthly_payment"]
            new = calculator.summary(app.amount, p.base_rate, longer, p.revolving)["monthly_payment"]
            return {"text": f"Сейчас ориентировочный платёж — {_money(now)}. Если увеличить срок до {longer} мес., "
                            f"он снизится примерно до {_money(new)}. Ещё можно уменьшить сумму или предложить залог — ставка будет ниже. "
                            f"В калькуляторе есть кнопка «Платёж слишком высокий» — я подберу условия под комфортный платёж.",
                    "actions": [_a("Открыть калькулятор", "/advisor")]}
        return {"text": "Платёж можно снизить тремя способами: увеличить срок, уменьшить сумму или предложить залог. "
                        "Скажите комфортный платёж в калькуляторе — я подберу сумму и срок.",
                "actions": [_a("Калькулятор", "/advisor")]}

    if has(r"статус", r"что с (моей )?заявк", r"где (моя )?заявк", r"когда (будет )?решени", r"сколько ждать"):
        if not app:
            return {"text": "У вас пока нет заявок. Давайте подберём кредит — это займёт пару минут.",
                    "actions": [_a("Подобрать кредит", "/advisor")]}
        st = STAGES[Status(app.status)]
        eta = f" Обычно это занимает {st['eta']}." if st.get("eta") else ""
        todo = f" Что нужно от вас: {st['todo'].lower()}." if st.get("todo") else ""
        return {"text": f"Заявка {app.number} — «{LABELS[Status(app.status)]}». {st['say']}{eta}{todo}",
                "actions": [_a("Открыть заявку", f"/applications/{app.id}")]}

    if has(r"почему (мне )?отказ", r"причин\w* отказ", r"отказал", r"не одобрил"):
        if app and app.status == Status.REJECTED and app.decision:
            reasons = app.decision.get("reasons", [])
            tips = [tip for r in reasons for tip in r.get("tips", [])]
            text = "Основная причина: " + "; ".join(r["text"] for r in reasons) + "."
            if tips:
                text += " Что можно сделать: " + "; ".join(tips) + "."
            return {"text": text, "actions": [_a("Проверить шансы заново", "/precheck")]}
        return {"text": "Отказов по вашим заявкам нет. Если хотите заранее понять, что влияет на решение, — пройдите быструю оценку шансов.",
                "actions": [_a("Узнать шансы", "/precheck")]}

    if has(r"документ", r"что (нужно )?загрузить", r"выписк", r"справк"):
        if app and app.requested_documents:
            from app.domain.products import DOCUMENT_TYPES
            docs = ", ".join(DOCUMENT_TYPES.get(d, d) for d in app.requested_documents)
            return {"text": f"По заявке {app.number} банк ждёт: {docs}. Загрузите их на странице заявки и нажмите «Отправить повторно».",
                    "actions": [_a("Загрузить документы", f"/applications/{app.id}")]}
        return {"text": "Для большинства заявок документы не нужны: сведения о компании я сам запрашиваю в ЕГРЮЛ, ФНС и БКИ. "
                        "Дополнительно могут понадобиться: договор поставки для инвестиционного кредита, госконтракт для тендерного, "
                        "выписка по счёту — для крупных сумм."}

    if has(r"шанс", r"одобрят ли", r"дадут ли", r"вероятност"):
        return {"text": "Пройдите короткую оценку готовности: 8 вопросов о бизнесе — и я покажу, что помогает и что мешает одобрению. "
                        "Это ориентир, а не обещание банка, и он не влияет на кредитную историю.",
                "actions": [_a("Узнать шансы", "/precheck")]}

    if has(r"бки", r"кредитн\w* истори"):
        return {"text": "Кредитная история хранится в бюро кредитных историй (БКИ): там видно, какие у бизнеса кредиты и были ли просрочки. "
                        "Банк запрашивает её только с вашего согласия — его вы даёте на последнем шаге заявки. "
                        "Сама проверка шансов в кабинете в БКИ не обращается."}

    if has(r"подпис", r"\bпэп\b", r"код подтвержд"):
        return {"text": "Договор подписывается простой электронной подписью прямо в кабинете: после принятия условий я покажу код "
                        "подтверждения — введите его, и деньги поступят на счёт. Ездить в офис не нужно."}

    if has(r"овердрафт"):
        p = PRODUCTS["OVERDRAFT"]
        return {"text": f"Овердрафт — это «подушка» на расчётном счёте: если денег не хватает на платёж, банк доплатит до лимита, "
                        f"а вы вернёте с ближайших поступлений. Проценты (от {p.base_rate:g}%) — только за дни использования. "
                        f"Хорош для кассовых разрывов, не для крупных покупок."}

    if has(r"залог"):
        return {"text": "Залог — имущество, которое страхует кредит: недвижимость, оборудование, транспорт. "
                        "Для инвестиционного кредита залогом обычно служит само покупаемое оборудование. "
                        "С залогом можно получить больше и дешевле, но он не обязателен для экспресс-кредита и овердрафта."}

    if has(r"тендер", r"госконтракт", r"44-фз", r"223-фз"):
        return {"text": "Для исполнения госконтракта есть отдельный кредит: деньги на закупку и работы, а погашение — "
                        "из оплаты заказчика. Понадобится сам контракт или протокол победы в тендере.",
                "actions": [_a("Подобрать кредит", "/advisor")]}

    if has(r"ставк", r"процент", r"переплат"):
        rates = ", ".join(f"{p.name.lower()} — от {p.base_rate:g}%" for p in PRODUCTS.values())
        return {"text": f"Базовые ставки: {rates}. Итоговая ставка зависит от оценки риска и залога — "
                        f"её вы увидите в предложении банка до подписания."}

    if has(r"как(ой|ую)? кредит", r"подобр", r"что выбрать", r"какой продукт"):
        return {"text": "Расскажите, на что нужны деньги, — я подберу продукт и объясню, почему он подходит.",
                "actions": [_a("Подобрать кредит", "/advisor")]}

    if has(r"оператор", r"живой человек", r"сотрудник", r"специалист"):
        return {"text": "Если заявка нестандартная, её всегда смотрит кредитный специалист — это происходит автоматически. "
                        "Свой вопрос можно оставить здесь: я передам его вместе с контекстом заявки."}

    if has(r"спасибо", r"благодар"):
        return {"text": "Пожалуйста! Я рядом, если что-то понадобится 🙂"}
    return None


# --- LLM ---------------------------------------------------------------------

def llm_status() -> dict:
    s = get_settings()
    if not s.llm_enabled:
        return {"enabled": False, "available": False, "model": s.llm_model}
    try:
        r = httpx.get(f"{s.llm_url}/api/tags", timeout=2)
        models = [m.get("name") for m in r.json().get("models", [])]
        return {"enabled": True, "available": any(m and m.startswith(s.llm_model.split(":")[0]) for m in models),
                "model": s.llm_model, "models": models}
    except Exception:  # noqa: BLE001
        return {"enabled": True, "available": False, "model": s.llm_model}


def llm_answer(text: str, user: User, app: Application | None, history: list[ChatMessage]) -> str | None:
    s = get_settings()
    if not s.llm_enabled:
        return None
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(catalog=_catalog(), context=_context(user, app))}]
    messages += [{"role": m.role, "content": m.content} for m in history[-6:]]
    messages.append({"role": "user", "content": text})
    try:
        r = httpx.post(f"{s.llm_url}/api/chat", timeout=s.llm_timeout_s, json={
            "model": s.llm_model, "messages": messages, "stream": False,
            "options": {"temperature": 0.3, "num_predict": 300},
        })
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "").strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("llm_unavailable error=%s", exc)
        return None
    if not content:
        return None
    # Пост-фильтр: ассистент не имеет права обещать одобрение
    if FORBIDDEN.search(content):
        content = FORBIDDEN.sub("", content) + "\n\nВажно: решение принимает банк после проверки, заранее его гарантировать нельзя."
    return content[:1500]


FALLBACK = {
    "text": "Хм, этого я пока не знаю 🙈 Я умею подобрать кредит, оценить шансы, рассказать о статусе заявки, "
            "документах, ставках, залоге и подписании. Попробуйте спросить иначе или выберите действие:",
    "actions": [_a("Подобрать кредит", "/advisor"), _a("Узнать шансы", "/precheck"), _a("Мои заявки", "/applications")],
}


def answer(db: Session, user: User, text: str, application_id: int | None = None) -> ChatMessage:
    app = _active_application(db, user, application_id)
    history = db.scalars(
        select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(6)
    ).all()[::-1]
    db.add(ChatMessage(user_id=user.id, role="user", content=text))

    result = rule_answer(text, user, app)
    source = "rules"
    if result is None:
        llm = llm_answer(text, user, app, list(history))
        if llm:
            result, source = {"text": llm, "actions": []}, "llm"
        else:
            result, source = FALLBACK, "fallback"
    msg = ChatMessage(user_id=user.id, role="assistant", content=result["text"], source=source,
                      meta={"actions": result.get("actions", [])})
    db.add(msg)
    db.commit()
    return msg
