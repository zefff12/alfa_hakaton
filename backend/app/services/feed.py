"""«Лента Альфика» — персональная лента новостей и советов.

Ранжирование прозрачно: каждая карточка набирает баллы за совпадение с
профилем клиента (отрасль, этап заявки, продукт, размер бизнеса) и показывает
причину «Почему вы это видите». Скрытые карточки больше не показываются,
понравившиеся темы поднимаются выше. Контент демонстрационный.
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, FeedInteraction, User

INDUSTRY_LABELS = {
    "food": "общепит и производство продуктов", "retail": "розничная торговля", "construction": "строительство",
    "services": "услуги", "it": "ИТ", "transport": "транспорт и логистика", "manufacturing": "производство",
    "medicine": "медицина", "agro": "сельское хозяйство",
}

STAGE_OF = {
    "DRAFT": "draft", "SUBMITTED": "in_review", "DATA_CHECK": "in_review", "ENRICHMENT": "in_review",
    "SCORING": "in_review", "MANUAL_REVIEW": "in_review", "INFO_REQUESTED": "info_requested",
    "APPROVED": "offer", "COUNTER_OFFER": "offer", "SIGNING": "offer", "ISSUING": "offer",
    "REJECTED": "rejected", "DISBURSED": "borrower", "CANCELLED": "none",
}

@dataclass
class Item:
    id: str
    kind: str  # news | tip | offer | guide
    title: str
    body: str
    tags: set[str] = field(default_factory=set)  # topic tags
    industries: set[str] = field(default_factory=set)
    stages: set[str] = field(default_factory=set)
    products: set[str] = field(default_factory=set)
    cta: dict | None = None
    base: int = 10

ITEMS: list[Item] = [
    Item("seasonal-retail", "tip", "Готовимся к праздничному сезону: закупка заранее",
         "За 6–8 недель до пикового сезона розничные бизнесы наращивают запасы. Оборотный кредит позволяет купить товар "
         "по ценам до подорожания и вернуть деньги из выручки сезона.",
         {"working_capital"}, {"retail", "food"}, set(), {"WORKING"}, {"label": "Подобрать кредит", "to": "/advisor?purpose=working_capital"}),
    Item("bakery-equipment", "guide", "Новая печь или линия: как посчитать окупаемость",
         "Простое правило: ежемесячный платёж по кредиту должен быть меньше дополнительной прибыли от оборудования. "
         "Альфик посчитает платёж за минуту — а залогом станет само оборудование.",
         {"equipment"}, {"food", "manufacturing"}, set(), {"INVEST"}, {"label": "Калькулятор", "to": "/advisor?purpose=equipment"}),
    Item("construction-gap", "tip", "Кассовые разрывы в строительстве: как пережить отсрочку оплаты",
         "Заказчики платят по актам, а материалы и зарплату нужно оплачивать сейчас. Овердрафт закрывает разрыв, "
         "а проценты начисляются только за дни использования.",
         {"cash_gap"}, {"construction", "transport"}, set(), {"OVERDRAFT"}, {"label": "Что такое овердрафт", "to": "/advisor?purpose=cash_gap"}),
    Item("tender-finance", "offer", "Выиграли тендер? Деньги на исполнение контракта",
         "Кредит на исполнение госконтракта: погашение из оплаты заказчика, без залога. Нужен только контракт.",
         {"contract"}, {"construction", "it", "manufacturing", "services", "medicine"}, set(), {"TENDER"},
         {"label": "Подробнее", "to": "/advisor?purpose=contract"}),
    Item("flowers-holidays", "tip", "Цветочный бизнес: 8 Марта и 1 сентября — пик выручки",
         "Перед пиковыми датами выгодно заранее договориться о поставках. Экспресс-кредит без залога одобряется онлайн.",
         {"working_capital"}, {"retail"}, set(), {"EXPRESS"}, {"label": "Узнать шансы", "to": "/precheck"}),
    Item("it-teams", "guide", "Рост ИТ-команды без кассового разрыва",
         "Заказчики платят по этапам, а зарплаты — каждый месяц. Разберитесь, когда лучше овердрафт, а когда — кредит на развитие.",
         {"expansion"}, {"it", "services"}, set(), {"OVERDRAFT", "EXPRESS"}),
    Item("medicine-equipment", "guide", "Оборудование для клиники: лизинг или кредит?",
         "Сравниваем стоимость, налоговый эффект и требования к залогу на примере стоматологической установки.",
         {"equipment"}, {"medicine"}, set(), {"INVEST"}),
    Item("prepare-docs", "guide", "Что подготовить, чтобы заявку одобрили быстрее",
         "Большую часть данных банк получает сам из ЕГРЮЛ, ФНС и БКИ. Подготовьте выписку по счёту за 6 месяцев — "
         "она подтвердит реальные обороты, если они отличаются от отчётности.",
         {"docs"}, set(), {"none", "draft", "info_requested"}, set(), {"label": "Узнать шансы", "to": "/precheck"}, base=14),
    Item("how-scoring", "guide", "Как банк оценивает заявку: простое объяснение скоринга",
         "Срок работы, обороты, долговая нагрузка, платёжная дисциплина. Рассказываем, какие факторы важнее всего "
         "и как их улучшить.", {"scoring"}, set(), {"none", "draft", "rejected", "in_review"}, set(), base=12),
    Item("in-review-wait", "news", "Ваша заявка в работе — вот что происходит сейчас",
         "Банк проверяет данные и запрашивает сведения в государственных реестрах и бюро кредитных историй. "
         "Повторно отправлять документы не нужно — Альфик сообщит, если что-то понадобится.",
         {"status"}, set(), {"in_review"}, set(), base=30),
    Item("info-needed", "news", "Не хватает одного документа — и заявка пойдёт дальше",
         "Загрузите запрошенный документ на странице заявки. Как только файл появится, проверка продолжится автоматически.",
         {"status"}, set(), {"info_requested"}, set(), {"label": "Мои заявки", "to": "/applications"}, base=40),
    Item("offer-ready", "news", "Предложение банка действует 30 дней",
         "Посмотрите условия и выберите удобный вариант. Подписать договор можно прямо в кабинете.",
         {"status"}, set(), {"offer"}, set(), {"label": "Мои заявки", "to": "/applications"}, base=40),
    Item("rejected-plan", "guide", "Отказ — не навсегда: план на 3 месяца",
         "Что сделать, чтобы следующая заявка прошла: снизить долговую нагрузку, закрыть просрочки и налоговые долги, "
         "подтвердить обороты выпиской.", {"scoring"}, set(), {"rejected"}, set(), {"label": "Проверить шансы", "to": "/precheck"}, base=35),
    Item("borrower-early", "tip", "Досрочное погашение без комиссий",
         "Если выручка выросла — можно погасить кредит досрочно частично или полностью, проценты пересчитаются.",
         {"repayment"}, set(), {"borrower"}, set(), base=30),
    Item("borrower-next", "offer", "Для заёмщиков с хорошей историей — повторный кредит быстрее",
         "После 6 платежей без просрочек повторная заявка рассматривается по упрощённой схеме.",
         {"repeat"}, set(), {"borrower"}, set(), base=20),
    Item("transport-fuel", "tip", "Транспортным компаниям: топливо и ремонт без остановки рейсов",
         "Оборотный кредит или овердрафт помогут оплатить топливо и ремонт до поступления оплаты от клиентов.",
         {"cash_gap"}, {"transport"}, set(), {"OVERDRAFT", "WORKING"}),
    Item("first-loan", "guide", "Первый кредит для бизнеса: 5 вопросов, которые стоит задать себе",
         "На что нужны деньги, когда они вернутся, какой платёж комфортен, есть ли залог и запас на непредвиденное.",
         {"basics"}, set(), {"none"}, set(), {"label": "Подобрать кредит", "to": "/advisor"}, base=18),
]

def _profile(db: Session, user: User) -> dict:
    apps = db.scalars(select(Application).where(Application.company_id == user.company_id)
                      .order_by(Application.updated_at.desc())).all()
    latest = apps[0] if apps else None
    stage = STAGE_OF.get(latest.status, "none") if latest else "none"
    return {
        "industry": (user.company.industry if user.company else None) or "other",
        "stage": stage,
        "product": latest.product_code if latest else None,
        "purpose": latest.purpose if latest else None,
        "status": latest.status if latest else None,
    }

def build(db: Session, user: User, limit: int = 8) -> dict:
    prof = _profile(db, user)
    interactions = db.scalars(select(FeedInteraction).where(FeedInteraction.user_id == user.id)).all()
    hidden = {i.item_id for i in interactions if i.action == "hide"}
    liked_tags = {tag for i in interactions if i.action == "like"
                  for it in ITEMS if it.id == i.item_id for tag in it.tags}

    ranked = []
    for it in ITEMS:
        if it.id in hidden:
            continue
        if it.stages and prof["stage"] not in it.stages:
            continue
        score, reasons = it.base, []
        if it.industries:
            if prof["industry"] in it.industries:
                score += 25
                reasons.append(f"ваша отрасль — {INDUSTRY_LABELS.get(prof['industry'], prof['industry'])}")
            else:
                score -= 15
        if it.stages:
            score += 10
            reasons.append(_stage_reason(prof["stage"]))
        if prof["product"] and prof["product"] in it.products:
            score += 15
            reasons.append("связано с продуктом из вашей заявки")
        if prof["purpose"] and prof["purpose"] in it.tags:
            score += 10
            reasons.append("совпадает с целью кредита")
        if it.tags & liked_tags:
            score += 12
            reasons.append("вам понравились похожие материалы")
        ranked.append((score, it, reasons))

    ranked.sort(key=lambda x: x[0], reverse=True)
    items = [{
        "id": it.id, "kind": it.kind, "title": it.title, "body": it.body, "cta": it.cta, "score": score,
        "why": ("Вы видите это, потому что " + ", ".join(reasons)) if reasons else "Популярное у предпринимателей",
    } for score, it, reasons in ranked[:limit]]
    return {"profile": {**prof, "industry_label": INDUSTRY_LABELS.get(prof["industry"], "другая отрасль")}, "items": items}

def _stage_reason(stage: str) -> str:
    return {
        "none": "у вас пока нет заявок", "draft": "вы заполняете заявку", "in_review": "ваша заявка на рассмотрении",
        "info_requested": "банк ждёт от вас документы", "offer": "у вас есть предложение банка",
        "rejected": "по последней заявке был отказ", "borrower": "у вас есть действующий кредит",
    }.get(stage, "этап вашей заявки")

def react(db: Session, user: User, item_id: str, action: str) -> None:
    if not any(i.id == item_id for i in ITEMS):
        return
    db.add(FeedInteraction(user_id=user.id, item_id=item_id, action=action))
    db.commit()

