"""API личного кабинета клиента."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain import advisor, calculator, readiness
from app.domain.decision import offer_rate
from app.domain.products import DOCUMENT_TYPES, PRODUCTS, PURPOSES, get_product
from app.integrations import clients
from app.models import Application, ChatMessage, Document, Notification, User
from app.schemas import (AcceptOfferRequest, AdvisorRequest, ApplicationAction, ApplicationCreate, ApplicationUpdate, IntakeCreateRequest, IntakeRequest, FixRequest, MatchProfileUpdate, OfferApplyRequest, SwipeRequest,
                         CalcRequest, ChatMessageOut, ChatRequest, EgrulLookupOut, FeedReaction, NotificationOut,
                         PrecheckRequest, SignRequest)
from app.security import current_user, require_client
from app.services import applications as svc
from app.services import assistant, feed, intake
from app.services import match as match_svc

router = APIRouter(prefix="/api", tags=["Кабинет клиента"])


# --- Справочники и калькуляторы ---------------------------------------------

@router.get("/catalog", tags=["Справочники"], summary="Каталог продуктов, цели и типы документов")
def catalog():
    return {
        "products": [p.to_dict() for p in PRODUCTS.values()],
        "purposes": [{"code": k, "label": v} for k, v in PURPOSES.items()],
        "document_types": [{"code": k, "label": v} for k, v in DOCUMENT_TYPES.items()],
    }


@router.post("/advisor/recommend", tags=["Альфик"], summary="Подбор продукта под задачу бизнеса")
def recommend(req: AdvisorRequest):
    return advisor.recommend(advisor.NeedProfile(**req.model_dump()))


@router.post("/calculator", tags=["Справочники"], summary="Расчёт платежа и подбор условий под комфортный платёж")
def calc(req: CalcRequest):
    product = get_product(req.product_code)
    if not product:
        raise HTTPException(404, "Продукт не найден")
    rate = offer_rate(product, "B", req.has_collateral) if req.has_collateral else product.base_rate
    result = {"product_code": product.code, **calculator.summary(req.amount, rate, req.term_months, product.revolving)}
    if req.comfortable_payment and not product.revolving:
        p = req.comfortable_payment
        options = []
        term = calculator.min_term_for_payment(req.amount, rate, p, product.max_term)
        if term:
            options.append({"label": f"Та же сумма на {term} мес.",
                            **calculator.summary(req.amount, rate, term)})
        amount = calculator.round_amount(min(calculator.max_amount_for_payment(p, rate, req.term_months), product.max_amount))
        if amount >= product.min_amount:
            options.append({"label": f"Сумма поменьше на {req.term_months} мес.",
                            **calculator.summary(amount, rate, req.term_months)})
        max_amount = calculator.round_amount(min(calculator.max_amount_for_payment(p, rate, product.max_term), product.max_amount))
        if max_amount >= product.min_amount and product.max_term != req.term_months:
            options.append({"label": f"Максимум на {product.max_term} мес.",
                            **calculator.summary(max_amount, rate, product.max_term)})
        result["alternatives"] = options
    return result


@router.post("/precheck", tags=["Альфик"], summary="«Каковы мои шансы?» — предварительная оценка готовности")
def precheck(req: PrecheckRequest, user: User = Depends(require_client)):
    product = get_product(req.product_code)
    if not product:
        raise HTTPException(404, "Продукт не найден")
    data = req.model_dump(exclude={"product_code"})
    industry = (user.company.industry if user.company else None) or "other"
    return readiness.evaluate(readiness.PrecheckAnswers(product=product, industry=industry, **data))


@router.get("/company/lookup/{inn}", response_model=EgrulLookupOut, tags=["Справочники"],
            summary="Автозаполнение реквизитов по ИНН (ЕГРЮЛ)")
def lookup(inn: str, user: User = Depends(current_user)):
    try:
        data = clients.fetch_egrul(inn)
    except clients.IntegrationError as exc:
        raise HTTPException(503, f"Не удалось получить данные: {exc.message}")
    return EgrulLookupOut(inn=inn, name=data.get("name"), data=data)


# --- Заявки ------------------------------------------------------------------

@router.get("/applications", summary="Мои заявки")
def list_apps(user: User = Depends(require_client), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.company_id == user.company_id)
                      .order_by(Application.created_at.desc())).all()
    return [svc.serialize(a) for a in apps]


@router.post("/applications", status_code=201, summary="Создать черновик заявки")
def create_app(req: ApplicationCreate, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(svc.create(db, user, req))


@router.get("/applications/{app_id}", summary="Карточка заявки")
def get_app(app_id: int, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(svc.get_owned(db, user, app_id))


@router.patch("/applications/{app_id}", summary="Обновить черновик (автосохранение)")
def patch_app(app_id: int, req: ApplicationUpdate, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(svc.update_draft(db, user, svc.get_owned(db, user, app_id), req))


@router.get("/applications/{app_id}/validate", summary="Проверить готовность черновика к отправке")
def validate_app(app_id: int, user: User = Depends(require_client), db: Session = Depends(get_db)):
    errors = svc.validate_for_submit(svc.get_owned(db, user, app_id))
    return {"ok": not errors, "errors": errors}


@router.post("/applications/{app_id}/submit", summary="Отправить заявку в банк")
def submit_app(app_id: int, req: ApplicationAction, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(svc.submit(db, user, svc.get_owned(db, user, app_id), req.version))


@router.post("/applications/{app_id}/resubmit", summary="Отправить повторно после запроса данных")
def resubmit_app(app_id: int, req: ApplicationAction, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(svc.resubmit(db, user, svc.get_owned(db, user, app_id), req.version, req.comment))


@router.post("/applications/{app_id}/accept", summary="Принять предложение банка")
def accept(app_id: int, req: AcceptOfferRequest, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(svc.accept_offer(db, user, svc.get_owned(db, user, app_id), req.option_id, req.version))


@router.post("/applications/{app_id}/sign", summary="Подписать договор кодом ПЭП")
def sign(app_id: int, req: SignRequest, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(svc.sign(db, user, svc.get_owned(db, user, app_id), req.code, req.version))


@router.post("/applications/{app_id}/cancel", summary="Отменить заявку / отказаться от предложения")
def cancel(app_id: int, req: ApplicationAction, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(svc.cancel(db, user, svc.get_owned(db, user, app_id), req.version, req.comment))


@router.post("/applications/{app_id}/documents", status_code=201, summary="Загрузить документ")
async def upload(app_id: int, doc_type: str = Form(...), file: UploadFile = File(...),
                 user: User = Depends(require_client), db: Session = Depends(get_db)):
    app = svc.get_owned(db, user, app_id)
    await svc.upload_document(db, user, app, doc_type, file)
    return svc.serialize(app)


@router.get("/documents/{doc_id}/download", tags=["Документы"], summary="Скачать документ")
def download(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc or (user.role == "client" and doc.application.company_id != user.company_id):
        raise HTTPException(404, "Документ не найден")
    return FileResponse(doc.storage_path, media_type=doc.content_type, filename=doc.filename)


# --- Альфик, лента, уведомления -------------------------------------------------

@router.post("/assistant/chat", response_model=ChatMessageOut, tags=["Альфик"], summary="Вопрос Альфику")
def chat(req: ChatRequest, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return assistant.answer(db, user, req.message.strip(), req.application_id)


@router.post("/intake/message", tags=["Альфик"], summary="«Расскажите Альфику»: разбор рассказа клиента в параметры заявки")
def intake_message(req: IntakeRequest, user: User = Depends(require_client)):
    return intake.step(user, req.message.strip(), req.state)


@router.get("/intake/examples", tags=["Альфик"], summary="Примеры фраз для диалога")
def intake_examples():
    return {"examples": intake.examples()}


@router.post("/intake/create", status_code=201, tags=["Альфик"], summary="Создать черновик заявки из диалога")
def intake_create(req: IntakeCreateRequest, user: User = Depends(require_client), db: Session = Depends(get_db)):
    if not (req.state.get("fields") or {}).get("amount"):
        raise HTTPException(422, "Сначала расскажите, сколько денег нужно")
    return svc.serialize(intake.create_application(db, user, req.state, req.product_code))


# --- «Кредитный подбор»: свайпы, избранное, сравнение ---------------------------

@router.get("/match", tags=["Кредитный подбор"], summary="Колода предложений с учётом приоритетов и свайпов")
def match_deck(user: User = Depends(require_client), db: Session = Depends(get_db)):
    return match_svc.deck(db, user)


@router.put("/match/profile", tags=["Кредитный подбор"], summary="Изменить параметры подбора")
def match_profile(req: MatchProfileUpdate, user: User = Depends(require_client), db: Session = Depends(get_db)):
    match_svc.save_profile(db, user, req.model_dump())
    return match_svc.deck(db, user)


@router.post("/match/swipe", tags=["Кредитный подбор"], summary="Свайп: вправо — в избранное, влево — пропустить")
def match_swipe(req: SwipeRequest, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return match_svc.swipe(db, user, req.product_code, req.action)


@router.get("/favorites", tags=["Кредитный подбор"], summary="Избранные предложения")
def favorites_list(user: User = Depends(require_client), db: Session = Depends(get_db)):
    return match_svc.favorites(db, user)


@router.post("/favorites/{code}", status_code=201, tags=["Кредитный подбор"], summary="Добавить в избранное")
def favorites_add(code: str, user: User = Depends(require_client), db: Session = Depends(get_db)):
    match_svc.add_favorite(db, user, code)
    return match_svc.favorites(db, user)


@router.delete("/favorites/{code}", tags=["Кредитный подбор"], summary="Убрать из избранного")
def favorites_remove(code: str, user: User = Depends(require_client), db: Session = Depends(get_db)):
    match_svc.remove_favorite(db, user, code)
    return match_svc.favorites(db, user)


@router.delete("/favorites", tags=["Кредитный подбор"], summary="Очистить избранное")
def favorites_clear(user: User = Depends(require_client), db: Session = Depends(get_db)):
    match_svc.remove_favorite(db, user, None)
    return match_svc.favorites(db, user)


@router.post("/favorites/{code}/compare", tags=["Кредитный подбор"], summary="Включить/исключить из сравнения")
def favorites_compare_toggle(code: str, user: User = Depends(require_client), db: Session = Depends(get_db)):
    match_svc.toggle_compare(db, user, code)
    return match_svc.favorites(db, user)


@router.get("/compare", tags=["Кредитный подбор"], summary="Сравнение предложений")
def compare(codes: str | None = None, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return match_svc.compare(db, user, [c for c in (codes or "").split(",") if c] or None)


@router.get("/offers/{code}", tags=["Кредитный подбор"], summary="Подробнее о предложении")
def offer_detail(code: str, amount: int | None = None, term: int | None = None,
                 user: User = Depends(require_client), db: Session = Depends(get_db)):
    return match_svc.detail(db, user, code, amount, term)


@router.post("/offers/{code}/apply", status_code=201, tags=["Кредитный подбор"], summary="Оформить заявку по предложению")
def offer_apply(code: str, req: OfferApplyRequest, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.serialize(match_svc.apply(db, user, code, req.amount, req.term_months))


# --- Проверка документов и анкеты ---------------------------------------------

@router.get("/applications/{app_id}/checks", tags=["Документы"], summary="Проверка документов и анкеты на несоответствия")
def app_checks(app_id: int, user: User = Depends(require_client), db: Session = Depends(get_db)):
    return svc.checks(svc.get_owned(db, user, app_id))


@router.post("/applications/{app_id}/fix", tags=["Документы"], summary="Исправить анкету по подсказке Альфика")
def app_fix(app_id: int, req: FixRequest, user: User = Depends(require_client), db: Session = Depends(get_db)):
    app = svc.apply_fix(db, user, svc.get_owned(db, user, app_id), req.field, req.value)
    return {"application": svc.serialize(app), "checks": svc.checks(app)}


@router.get("/me/capacity", tags=["Кабинет клиента"], summary="«Мои возможности»: предварительная сумма")
def capacity(user: User = Depends(require_client), db: Session = Depends(get_db)):
    last = db.scalar(select(Application).where(Application.company_id == user.company_id, Application.decision.is_not(None))
                     .order_by(Application.updated_at.desc()))
    limit = ((last.decision or {}).get("limit") if last else None)
    if limit:
        return {"amount": int(limit), "source": "scoring"}
    try:
        revenue = float(clients.fetch_fns(user.company.inn).get("annual_revenue") or 0)
    except clients.IntegrationError:
        return {"amount": None, "source": None}
    # Ориентир по обороту: четверть годовой выручки, не выше 10 млн — до проверки кредитной истории
    return {"amount": int(min(10_000_000, revenue * 0.25) // 100_000 * 100_000), "source": "fns"}


@router.get("/assistant/history", response_model=list[ChatMessageOut], tags=["Альфик"], summary="История диалога")
def chat_history(user: User = Depends(require_client), db: Session = Depends(get_db)):
    return db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(50)).all()[::-1]


@router.get("/assistant/status", tags=["Альфик"], summary="Доступность локальной LLM")
def chat_status():
    return {"rules": True, "llm": assistant.llm_status()}


@router.get("/feed", tags=["Лента"], summary="Персональная лента новостей и советов")
def get_feed(user: User = Depends(require_client), db: Session = Depends(get_db)):
    return feed.build(db, user)


@router.post("/feed/react", status_code=204, tags=["Лента"], summary="Реакция на карточку ленты")
def feed_react(req: FeedReaction, user: User = Depends(require_client), db: Session = Depends(get_db)):
    feed.react(db, user, req.item_id, req.action)


@router.get("/notifications", response_model=list[NotificationOut], tags=["Уведомления"], summary="Уведомления")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.id.desc()).limit(30)).all()


@router.post("/notifications/read-all", status_code=204, tags=["Уведомления"], summary="Отметить все прочитанными")
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id).values(is_read=True))
    db.commit()
