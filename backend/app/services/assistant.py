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
from app.domain.intake import parse as parse_story
from app.domain.intake_lang import to_canonical
from app.domain.products import DOCUMENT_TYPES, PRODUCTS, get_product
from app.i18n import L, get_lang, tr
from app.domain.state_machine import FINAL, LABELS, Status
from app.models import Application, ChatMessage, User
from app.services.alfik_texts import STAGES

log = logging.getLogger("assistant")

SYSTEM_PROMPT = """Ты — Альфик, дружелюбный помощник предпринимателя в кредитном кабинете банка.
Правила:
- Отвечай на языке: {language}. Коротко (до 5 предложений), простыми словами, без банковского жаргона.
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

    first_name = user.full_name.split()[0] if user.full_name else ""

    if has(r"^(привет|здравств|добр\w+ (день|утро|вечер)|хай)", r"^(hello|hi|hey|good (morning|afternoon|evening))\b",
           r"^(你好|您好|嗨|早上好|下午好|晚上好)"):
        return {"text": L(f"Привет, {first_name}! Я Альфик. Помогу выбрать кредит, оценить шансы, заполнить заявку и подскажу, "
                          f"что происходит на каждом этапе. С чего начнём?",
                          f"Hi, {first_name}! I'm Alfik. I'll help you choose a loan, check your chances, fill in the application "
                          f"and explain what happens at every step. Where shall we start?",
                          f"{first_name}，您好！我是 Alfik。我可以帮您选择贷款、评估获批可能、填写申请，并说明每个环节的进展。从哪里开始呢？"),
                "actions": [_a(L("Рассказать о задаче", "Tell me about your task", "描述您的需求"), "/talk"),
                            _a(tr("Узнать шансы"), "/precheck")]}

    if has(r"платеж\w* (слишком |очень )?(больш|высок)", r"дорого", r"снизить платеж", r"уменьшить платеж",
           r"payment(s)? (is |are )?(too )?(high|big|expensive)", r"lower (the |my )?payment", r"too expensive",
           r"月供(太|很)?(高|多|贵)", r"降低月供", r"太贵"):
        if app and app.amount and app.term_months and get_product(app.product_code):
            p = get_product(app.product_code)
            longer = min(p.max_term, (app.term_months or 12) * 2)
            now = _money(calculator.summary(app.amount, p.base_rate, app.term_months, p.revolving)["monthly_payment"])
            new = _money(calculator.summary(app.amount, p.base_rate, longer, p.revolving)["monthly_payment"])
            return {"text": L(f"Сейчас ориентировочный платёж — {now}. Если увеличить срок до {longer} мес., он снизится примерно "
                              f"до {new}. Ещё можно уменьшить сумму или предложить залог — ставка будет ниже. В калькуляторе есть "
                              f"кнопка «Платёж слишком высокий» — я подберу условия под комфортный платёж.",
                              f"The estimated payment is now {now}. Extending the term to {longer} months brings it down to about "
                              f"{new}. You can also reduce the amount or offer collateral for a lower rate. The calculator has a "
                              f"“Payment too high” button — I'll match terms to a comfortable payment.",
                              f"目前预计月供为{now}。若将期限延长至{longer}个月，月供约降至{new}。也可以降低金额或提供抵押以获得更低利率。"
                              f"计算器里有“月供太高”按钮——我会按您能承受的月供匹配条件。"),
                    "actions": [_a(tr("Открыть калькулятор"), "/advisor")]}
        return {"text": L("Платёж можно снизить тремя способами: увеличить срок, уменьшить сумму или предложить залог. "
                          "Скажите комфортный платёж в калькуляторе — я подберу сумму и срок.",
                          "There are three ways to lower the payment: a longer term, a smaller amount or collateral. "
                          "Enter a comfortable payment in the calculator and I'll pick the amount and term.",
                          "降低月供有三种方法：延长期限、降低金额或提供抵押。在计算器中输入可承受的月供，我来匹配金额和期限。"),
                "actions": [_a(tr("Калькулятор"), "/advisor")]}

    if has(r"статус", r"что с (моей )?заявк", r"где (моя )?заявк", r"когда (будет )?решени", r"сколько ждать",
           r"\bstatus\b", r"where is my application", r"how long", r"when will .*decision", r"状态", r"进度", r"多久", r"什么时候.*结果"):
        if not app:
            return {"text": L("У вас пока нет заявок. Давайте подберём кредит — это займёт пару минут.",
                              "You don't have any applications yet. Let's find a loan — it takes a couple of minutes.",
                              "您还没有申请。我们来选择贷款吧——只需几分钟。"),
                    "actions": [_a(tr("Подобрать кредит"), "/advisor")]}
        st = STAGES[Status(app.status)]
        label = tr(LABELS[Status(app.status)])
        eta = L(f" Обычно это занимает {st['eta']}.", f" It usually takes {tr(st['eta'])}.", f"通常需要{tr(st['eta'])}。") if st.get("eta") else ""
        todo = L(f" Что нужно от вас: {st['todo'].lower()}.", f" What you need to do: {tr(st['todo'])}.",
                 f"您需要：{tr(st['todo'])}。") if st.get("todo") else ""
        return {"text": L(f"Заявка {app.number} — «{label}». ", f"Application {app.number} — “{label}”. ",
                          f"申请 {app.number}——“{label}”。") + tr(st["say"]) + eta + todo,
                "actions": [_a(tr("Открыть заявку"), f"/applications/{app.id}")]}

    if has(r"почему (мне )?отказ", r"причин\w* отказ", r"отказал", r"не одобрил", r"why .*(reject|declin|refus)",
           r"rejected", r"declined", r"为什么.*拒", r"被拒", r"拒绝"):
        if app and app.status == Status.REJECTED and app.decision:
            reasons = app.decision.get("reasons", [])
            tips = [tr(tip) for r in reasons for tip in r.get("tips", [])]
            sep = L("; ", "; ", "；")
            text = L("Основная причина: ", "The main reason: ", "主要原因：") + sep.join(tr(r["text"]) for r in reasons) + "."
            if tips:
                text += L(" Что можно сделать: ", " What you can do: ", "可以这样做：") + sep.join(tips) + "."
            return {"text": text, "actions": [_a(tr("Проверить шансы заново"), "/precheck")]}
        return {"text": L("Отказов по вашим заявкам нет. Если хотите заранее понять, что влияет на решение, — пройдите быструю оценку шансов.",
                          "None of your applications have been declined. To see in advance what affects the decision, take the quick chances check.",
                          "您的申请都没有被拒绝。想提前了解影响审批的因素，可以做一次快速评估。"),
                "actions": [_a(tr("Узнать шансы"), "/precheck")]}

    if has(r"документ", r"что (нужно )?загрузить", r"выписк", r"справк", r"\bdocuments?\b", r"what (should|do) i upload",
           r"statement", r"文件", r"材料", r"上传", r"流水"):
        if app and app.requested_documents:
            docs = L(", ", ", ", "、").join(tr(DOCUMENT_TYPES.get(d, d)) for d in app.requested_documents)
            return {"text": L(f"По заявке {app.number} банк ждёт: {docs}. Загрузите их на странице заявки и нажмите «Отправить повторно».",
                              f"For application {app.number} the bank is waiting for: {docs}. Upload them on the application page and click “Resubmit”.",
                              f"申请 {app.number} 需要：{docs}。请在申请页面上传并点击“重新提交”。"),
                    "actions": [_a(tr("Загрузить документы"), f"/applications/{app.id}")]}
        return {"text": L("Для большинства заявок документы не нужны: сведения о компании я сам запрашиваю в ЕГРЮЛ, ФНС и БКИ. "
                          "Дополнительно могут понадобиться: договор поставки для инвестиционного кредита, госконтракт для тендерного, "
                          "выписка по счёту — для крупных сумм. Выписку в формате 1С или CSV я прочитаю сам.",
                          "Most applications need no documents: I request company data from the state register, tax service and credit bureau myself. "
                          "You may additionally need a supply contract for an investment loan, the contract for a tender loan, "
                          "or a bank statement for larger amounts. I can read a 1C or CSV statement myself.",
                          "大多数申请无需提供文件：企业信息由我向国家登记簿、税务局和征信局查询。"
                          "另外可能需要：投资贷款的供货合同、政府合同贷款的合同、大额贷款的银行流水。1C或CSV格式的流水我可以自动读取。")}

    if has(r"шанс", r"одобрят ли", r"дадут ли", r"вероятност", r"chances?", r"will (i|we) (be|get) approved", r"probability",
           r"能批", r"批准", r"获批", r"通过率", r"可能性"):
        return {"text": L("Пройдите короткую оценку готовности: 8 вопросов о бизнесе — и я покажу, что помогает и что мешает одобрению. "
                          "Это ориентир, а не обещание банка, и он не влияет на кредитную историю.",
                          "Take the short readiness check: 8 questions about your business, and I'll show what helps and what hinders approval. "
                          "It's an estimate, not a promise from the bank, and it doesn't affect your credit history.",
                          "做一个简短的准备度评估：回答8个关于企业的问题，我会告诉您哪些因素有利、哪些不利于获批。"
                          "这只是参考，并非银行承诺，也不会影响信用记录。"),
                "actions": [_a(tr("Узнать шансы"), "/precheck")]}

    if has(r"бки", r"кредитн\w* истори", r"credit (history|bureau|report)", r"征信", r"信用记录", r"信用报告"):
        return {"text": L("Кредитная история хранится в бюро кредитных историй (БКИ): там видно, какие у бизнеса кредиты и были ли просрочки. "
                          "Банк запрашивает её только с вашего согласия — его вы даёте на последнем шаге заявки. "
                          "Сама проверка шансов в кабинете в БКИ не обращается.",
                          "Your credit history is kept by a credit bureau: it shows the business's loans and any delinquencies. "
                          "The bank requests it only with your consent, which you give at the last step of the application. "
                          "The chances check in your account does not contact the bureau.",
                          "信用记录保存在征信局：可以看到企业有哪些贷款以及是否有逾期。银行只有在您同意后才会查询——"
                          "您会在申请最后一步给出同意。个人中心的获批评估不会查询征信局。")}

    if has(r"подпис", r"\bпэп\b", r"код подтвержд", r"\bsign", r"signature", r"confirmation code", r"签", r"确认码", r"电子签名"):
        return {"text": L("Договор подписывается простой электронной подписью прямо в кабинете: после принятия условий я покажу код "
                          "подтверждения — введите его, и деньги поступят на счёт. Ездить в офис не нужно.",
                          "The agreement is signed with a simple electronic signature right in your account: after you accept the terms "
                          "I'll show a confirmation code — enter it and the money arrives in your account. No need to visit an office.",
                          "合同可直接在个人中心用简单电子签名签署：接受条件后我会显示确认码——输入后资金即到账。无需前往网点。")}

    if has(r"овердрафт", r"overdraft", r"透支"):
        p = PRODUCTS["OVERDRAFT"]
        return {"text": L(f"Овердрафт — это «подушка» на расчётном счёте: если денег не хватает на платёж, банк доплатит до лимита, "
                          f"а вы вернёте с ближайших поступлений. Проценты (от {p.base_rate:g}%) — только за дни использования. "
                          f"Хорош для кассовых разрывов, не для крупных покупок.",
                          f"An overdraft is a cushion on your business account: if there isn't enough money for a payment, the bank tops it up "
                          f"to the limit and you repay from the next inflows. Interest (from {p.base_rate:g}%) is charged only for the days used. "
                          f"Great for cash gaps, not for big purchases.",
                          f"透支额度是结算账户上的“备用金”：付款时资金不足，银行会在额度内垫付，您用后续回款归还。"
                          f"利息（{p.base_rate:g}%起）只按使用天数计算。适合应对现金流缺口，不适合大额采购。")}

    if has(r"залог", r"collateral", r"pledge", r"抵押"):
        return {"text": L("Залог — имущество, которое страхует кредит: недвижимость, оборудование, транспорт. "
                          "Для инвестиционного кредита залогом обычно служит само покупаемое оборудование. "
                          "С залогом можно получить больше и дешевле, но он не обязателен для экспресс-кредита и овердрафта.",
                          "Collateral is property that secures the loan: real estate, equipment, vehicles. "
                          "For an investment loan the equipment being purchased usually serves as collateral. "
                          "Collateral gets you more money at a lower rate, but it isn't required for an express loan or an overdraft.",
                          "抵押物是为贷款提供担保的财产：不动产、设备、车辆。投资贷款通常以所购设备作抵押。"
                          "有抵押可以贷得更多、利率更低，但快速贷款和透支额度不要求抵押。")}

    if has(r"тендер", r"госконтракт", r"44-фз", r"223-фз", r"tender", r"government contract", r"招标", r"中标", r"政府合同"):
        return {"text": L("Для исполнения госконтракта есть отдельный кредит: деньги на закупку и работы, а погашение — "
                          "из оплаты заказчика. Понадобится сам контракт или протокол победы в тендере.",
                          "There is a dedicated government contract loan: money for purchases and work, repaid from the customer's payment. "
                          "You'll need the contract itself or the tender award protocol.",
                          "履行政府合同有专门的贷款：用于采购和施工，以客户付款还款。需要提供合同或中标通知书。"),
                "actions": [_a(tr("Подобрать кредит"), "/advisor")]}

    if has(r"ставк", r"процент", r"переплат", r"\brates?\b", r"interest", r"利率", r"利息"):
        sep = L(", ", ", ", "，")
        rates = sep.join(L(f"{p.name.lower()} — от {p.base_rate:g}%", f"{tr(p.name)} — from {p.base_rate:g}%",
                           f"{tr(p.name)}——{p.base_rate:g}%起") for p in PRODUCTS.values())
        return {"text": L(f"Базовые ставки: {rates}. Итоговая ставка зависит от оценки риска и залога — её вы увидите в предложении банка до подписания.",
                          f"Base rates: {rates}. The final rate depends on the risk assessment and collateral — you'll see it in the bank's offer before signing.",
                          f"基准利率：{rates}。最终利率取决于风险评估和抵押情况——签约前会在银行报价中显示。")}

    if has(r"как(ой|ую)? кредит", r"подобр", r"что выбрать", r"какой продукт", r"which loan", r"what loan", r"recommend",
           r"哪(个|种)贷款", r"推荐", r"选什么"):
        return {"text": L("Расскажите, на что нужны деньги, — я подберу продукт и объясню, почему он подходит.",
                          "Tell me what the money is for and I'll pick a product and explain why it fits.",
                          "告诉我资金用途，我会为您推荐产品并说明原因。"),
                "actions": [_a(L("Рассказать о задаче", "Tell me about your task", "描述您的需求"), "/talk"),
                            _a(tr("Подобрать кредит"), "/advisor")]}

    if has(r"оператор", r"живой человек", r"сотрудник", r"специалист", r"operator", r"human", r"manager", r"人工", r"客服", r"经理"):
        return {"text": L("Если заявка нестандартная, её всегда смотрит кредитный специалист — это происходит автоматически. "
                          "Свой вопрос можно оставить здесь: я передам его вместе с контекстом заявки.",
                          "If an application is non-standard, a credit officer always reviews it — this happens automatically. "
                          "You can leave your question here and I'll pass it on with the application context.",
                          "特殊申请会自动转交信贷专员审核。您也可以在这里留言，我会连同申请信息一起转交。")}

    if has(r"спасибо", r"благодар", r"thank", r"thx", r"谢谢", r"感谢"):
        return {"text": L("Пожалуйста! Я рядом, если что-то понадобится 🙂", "You're welcome! I'm here if you need anything 🙂",
                          "不客气！有需要随时找我 🙂")}
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
    language = {"ru": "русский", "en": "английский", "zh": "китайский (упрощённые иероглифы)"}[get_lang()]
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(catalog=_catalog(), context=_context(user, app), language=language)}]
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


def fallback() -> dict:
    return {
        "text": L("Хм, этого я пока не знаю 🙈 Я умею подобрать кредит, оценить шансы, рассказать о статусе заявки, "
                  "документах, ставках, залоге и подписании. Попробуйте спросить иначе или выберите действие:",
                  "Hmm, I don't know that yet 🙈 I can find a loan, check your chances, tell you about your application status, "
                  "documents, rates, collateral and signing. Try asking differently or pick an action:",
                  "嗯，这个我还不知道 🙈 我可以帮您选择贷款、评估获批可能、查询申请状态，介绍文件、利率、抵押和签约。"
                  "换个问法试试，或选择一个操作："),
        "actions": [_a(tr("Подобрать кредит"), "/advisor"), _a(tr("Узнать шансы"), "/precheck"), _a(tr("Мои заявки"), "/applications")],
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
        # Клиент описал задачу своими словами — предлагаем собрать заявку из рассказа
        story = parse_story(to_canonical(text)[0])
        if story.get("amount") and story.get("purpose"):
            understood = L(", ", ", ", "，").join(tr(i.to_dict()["display"]) for i in story.items
                                                  if i.field in ("amount", "purpose", "term_months"))
            result = {"text": L(f"Похоже, вы описали задачу: {understood}. Давайте я соберу из этого заявку — "
                                f"уточню пару моментов и подберу продукт.",
                                f"Looks like you've described your task: {understood}. Let me build an application from it — "
                                f"I'll clarify a couple of details and pick a product.",
                                f"看起来您描述了需求：{understood}。我来据此生成申请——再确认几个细节并推荐产品。"),
                      "actions": [{"label": tr("Собрать заявку из рассказа"), "to": "/talk", "prefill": text}]}
    if result is None:
        llm = llm_answer(text, user, app, list(history))
        if llm:
            result, source = {"text": llm, "actions": []}, "llm"
        else:
            result, source = fallback(), "fallback"
    msg = ChatMessage(user_id=user.id, role="assistant", content=result["text"], source=source,
                      meta={"actions": result.get("actions", [])})
    db.add(msg)
    db.commit()
    return msg
