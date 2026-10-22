"""Сценарии работы с заявкой для клиента и сотрудника банка."""
import hashlib
import os
import uuid
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import calculator, statement
from app.domain.decision import build_offer
from app.domain.products import DOCUMENT_TYPES, PURPOSES, get_product, required_documents_for
from app.domain.state_machine import FINAL, LABELS, Actor, Status, TransitionError, allowed_targets
from app.models import Application, Company, Document, DocumentAnalysis, User, utcnow
from app.services import pipeline, summary
from app.services.alfik_texts import STAGES

# Этапы, которые показываются клиенту на «таймлайне» заявки
CLIENT_TRACK = [
    ("DRAFT", "Заявка"),
    ("CHECK", "Проверка"),
    ("DECISION", "Решение"),
    ("SIGNING", "Подписание"),
    ("DISBURSED", "Деньги на счёте"),
]
TRACK_OF = {
    "DRAFT": 0, "SUBMITTED": 1, "DATA_CHECK": 1, "ENRICHMENT": 1, "SCORING": 1, "MANUAL_REVIEW": 1,
    "INFO_REQUESTED": 1, "APPROVED": 2, "COUNTER_OFFER": 2, "REJECTED": 2, "SIGNING": 3, "ISSUING": 3,
    "DISBURSED": 5, "CANCELLED": 0,
}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def doc_label(code: str) -> str:
    return DOCUMENT_TYPES.get(code, code)


def serialize(app: Application, *, for_bank: bool = False) -> dict:
    product = get_product(app.product_code)
    stage = STAGES.get(Status(app.status), {})
    actor = Actor.UNDERWRITER if for_bank else Actor.CLIENT
    required_docs = required_documents_for(product, app.amount, app.purpose) if product else []
    data = {
        "id": app.id,
        "number": app.number,
        "status": app.status,
        "status_label": LABELS[Status(app.status)],
        "version": app.version,
        "is_final": Status(app.status) in FINAL,
        "product_code": app.product_code,
        "product_name": product.name if product else None,
        "purpose": app.purpose,
        "purpose_label": PURPOSES.get(app.purpose or "", None),
        "purpose_comment": app.purpose_comment,
        "amount": app.amount,
        "term_months": app.term_months,
        "has_collateral": app.has_collateral,
        "collateral_description": app.collateral_description,
        "form_data": app.form_data or {},
        "consents": app.consents or {},
        "precheck": app.precheck,
        "estimate": calculator.summary(app.amount, product.base_rate, app.term_months, product.revolving)
        if product and app.amount and app.term_months else None,
        "required_documents": [{"code": d, "label": doc_label(d)} for d in required_docs],
        "requested_documents": [{"code": d, "label": doc_label(d)} for d in (app.requested_documents or [])],
        "offer": app.offer,
        "decision": _client_decision(app.decision) if not for_bank else app.decision,
        "signing": {k: v for k, v in (app.signing or {}).items() if k != "code_hash"} or None,
        "loan": app.loan,
        "documents": [
            {"id": d.id, "doc_type": d.doc_type, "label": doc_label(d.doc_type), "filename": d.filename,
             "size_bytes": d.size_bytes, "status": d.status, "created_at": _iso(d.created_at),
             "analysis": {"status": d.analysis.status, "error": d.analysis.error} if d.analysis else None}
            for d in app.documents
        ],
        "timeline": [
            {"id": e.id, "from_status": e.from_status, "to_status": e.to_status, "actor_type": e.actor_type,
             "event_type": e.event_type, "message": e.message, "created_at": _iso(e.created_at),
             "to_label": LABELS.get(Status(e.to_status)) if e.to_status else None,
             **({"payload": e.payload, "actor_id": e.actor_id} if for_bank else {})}
            for e in app.events
        ],
        "track": {"steps": [label for _, label in CLIENT_TRACK], "current": TRACK_OF.get(app.status, 0)},
        "statement": latest_statement(app),
        "alfik": stage,
        "allowed_transitions": allowed_targets(app.status, actor),
        "company": {
            "id": app.company.id, "inn": app.company.inn, "name": app.company.name, "legal_form": app.company.legal_form,
            "okved": app.company.okved, "okved_name": app.company.okved_name, "industry": app.company.industry,
            "director": app.company.director, "address": app.company.address, "registered_at": app.company.registered_at,
            "ogrn": app.company.ogrn, "region": app.company.region,
        },
        "created_at": _iso(app.created_at),
        "updated_at": _iso(app.updated_at),
        "submitted_at": _iso(app.submitted_at),
        "decided_at": _iso(app.decided_at),
    }
    if for_bank:
        data.update({
            "data_check": app.data_check,
            "enrichment": app.enrichment,
            "scoring": app.scoring,
            "applicant": {"id": app.user.id, "full_name": app.user.full_name, "position": app.user.position},
            "summary": summary.build(app),
            "assigned_to": app.assigned_to,
        })
    return data


def _client_decision(decision: dict | None) -> dict | None:
    """Клиенту показываем причины и советы, но не внутренние правила и пороги."""
    if not decision:
        return None
    return {"outcome": decision.get("outcome"), "reasons": decision.get("reasons", [])}


def next_number(db: Session) -> str:
    count = db.scalar(select(func.count(Application.id))) or 0
    return f"{utcnow():%y%m}-{count + 1:05d}"


def get_owned(db: Session, user: User, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if not app or app.company_id != user.company_id:
        raise HTTPException(404, "Заявка не найдена")
    return app


def create(db: Session, user: User, payload) -> Application:
    app = Application(
        number=next_number(db), company_id=user.company_id, user_id=user.id, status=Status.DRAFT.value,
        product_code=payload.product_code, purpose=payload.purpose, amount=payload.amount,
        term_months=payload.term_months, form_data=payload.form_data or {}, precheck=payload.precheck,
        consents={}, requested_documents=[],
    )
    if payload.form_data and payload.form_data.get("has_collateral") is not None:
        app.has_collateral = bool(payload.form_data.get("has_collateral"))
    db.add(app)
    db.flush()
    pipeline.log_event(db, app, "CREATED", "Черновик заявки создан", actor=Actor.CLIENT, actor_id=user.id,
                       to_status=Status.DRAFT.value)
    db.commit()
    return app


def update_draft(db: Session, user: User, app: Application, payload) -> Application:
    if app.status != Status.DRAFT.value:
        raise HTTPException(409, "Редактировать можно только черновик")
    if payload.version is not None and payload.version != app.version:
        raise HTTPException(409, "Заявка изменилась в другой вкладке. Обновите страницу.")
    data = payload.model_dump(exclude_unset=True, exclude={"version"})
    for key in ("form_data", "consents"):
        if key in data and data[key] is not None:
            data[key] = {**(getattr(app, key) or {}), **data[key]}
    for key, value in data.items():
        setattr(app, key, value)
    if (data.get("consents") or {}).get("bki") and not (app.consents or {}).get("bki_consent_id"):
        app.consents = {**app.consents, "bki_consent_id": f"CNS-{uuid.uuid4().hex[:10]}",
                        "bki_consent_at": utcnow().isoformat()}
    app.version += 1
    db.commit()
    return app


def validate_for_submit(app: Application) -> list[str]:
    product = get_product(app.product_code)
    errors = []
    if not product:
        return ["Выберите кредитный продукт"]
    if not app.amount or not (product.min_amount <= app.amount <= product.max_amount):
        errors.append(f"Сумма должна быть от {product.min_amount:,} до {product.max_amount:,} ₽".replace(",", " "))
    if not app.term_months or not (product.min_term <= app.term_months <= product.max_term):
        errors.append(f"Срок должен быть от {product.min_term} до {product.max_term} мес.")
    if not app.purpose:
        errors.append("Укажите цель кредита")
    fd = app.form_data or {}
    if fd.get("monthly_revenue") in (None, ""):
        errors.append("Укажите среднемесячную выручку")
    if fd.get("monthly_expenses") in (None, ""):
        errors.append("Укажите среднемесячные расходы")
    consents = app.consents or {}
    if not consents.get("bki"):
        errors.append("Нужно согласие на запрос кредитной истории")
    if not consents.get("personal_data"):
        errors.append("Нужно согласие на обработку персональных данных")
    if product.collateral == "required" and not app.has_collateral:
        errors.append("Для этого продукта нужен залог — отметьте его на шаге «Параметры»")
    return errors


def submit(db: Session, user: User, app: Application, version: int | None) -> Application:
    errors = validate_for_submit(app)
    if errors:
        raise HTTPException(422, {"message": "Заявка заполнена не полностью", "errors": errors})
    _transition(db, app, Status.SUBMITTED, Actor.CLIENT, user.id, "Клиент отправил заявку", version)
    app.submitted_at = utcnow()
    db.commit()
    return app


def resubmit(db: Session, user: User, app: Application, version: int | None, comment: str | None) -> Application:
    missing = [d for d in app.requested_documents or [] if d not in pipeline.provided_doc_types(app)]
    if missing:
        raise HTTPException(422, {"message": "Загрузите запрошенные документы",
                                  "errors": [doc_label(d) for d in missing]})
    _transition(db, app, Status.SUBMITTED, Actor.CLIENT, user.id,
                comment or "Клиент предоставил дополнительные данные", version)
    app.requested_documents = []
    db.commit()
    return app


def accept_offer(db: Session, user: User, app: Application, option_id: str, version: int | None) -> Application:
    options = (app.offer or {}).get("options", [])
    option = next((o for o in options if o["id"] == option_id), None)
    if not option:
        raise HTTPException(422, "Выбранный вариант условий не найден")
    code = pipeline.generate_signing_code()
    _transition(db, app, Status.SIGNING, Actor.CLIENT, user.id,
                f"Клиент принял условия: {option['label']}", version, payload={"option": option})
    app.signing = {
        "option_id": option_id, "option": option, "accepted_at": utcnow().isoformat(),
        "documents": ["Кредитный договор", "График платежей", "Заявление на выдачу"],
        # Демо: код ПЭП показывается в интерфейсе (не SMS, по ограничениям кейса)
        "demo_code": code,
        "code_hash": hashlib.sha256(code.encode()).hexdigest(),
    }
    db.commit()
    return app


def sign(db: Session, user: User, app: Application, code: str, version: int | None) -> Application:
    signing = app.signing or {}
    if hashlib.sha256(code.encode()).hexdigest() != signing.get("code_hash"):
        raise HTTPException(422, "Неверный код подтверждения")
    _transition(db, app, Status.ISSUING, Actor.CLIENT, user.id, "Договор подписан простой электронной подписью", version)
    app.signing = {**signing, "signed_at": utcnow().isoformat(), "signature_id": f"PEP-{uuid.uuid4().hex[:12]}"}
    db.commit()
    return app


def cancel(db: Session, user: User, app: Application, version: int | None, comment: str | None) -> Application:
    _transition(db, app, Status.CANCELLED, Actor.CLIENT, user.id, comment or "Клиент отменил заявку", version)
    db.commit()
    return app


async def upload_document(db: Session, user: User, app: Application, doc_type: str, file: UploadFile) -> Document:
    if doc_type not in DOCUMENT_TYPES:
        raise HTTPException(422, "Неизвестный тип документа")
    if Status(app.status) not in (Status.DRAFT, Status.INFO_REQUESTED, Status.MANUAL_REVIEW):
        raise HTTPException(409, "На этом этапе документы не принимаются")
    s = get_settings()
    content = await file.read()
    if len(content) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Файл больше {s.max_upload_mb} МБ")
    if not content:
        raise HTTPException(422, "Файл пустой")
    allowed = {"application/pdf", "image/jpeg", "image/png", "text/plain", "text/csv",
               "application/vnd.ms-excel",  # так Windows-браузеры часто отдают .csv
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ctype = file.content_type or "application/octet-stream"
    if ctype not in allowed:
        raise HTTPException(415, "Поддерживаются PDF, JPG, PNG, TXT, CSV, XLSX, DOCX")
    os.makedirs(s.storage_dir, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()
    path = os.path.join(s.storage_dir, f"{app.id}_{uuid.uuid4().hex}")
    with open(path, "wb") as fh:
        fh.write(content)
    doc = Document(application_id=app.id, doc_type=doc_type, filename=os.path.basename(file.filename or "file")[:255],
                   content_type=ctype, size_bytes=len(content), sha256=digest, storage_path=path)
    db.add(doc)
    pipeline.log_event(db, app, "DOCUMENT_UPLOADED", f"Загружен документ: {doc_label(doc_type)}",
                       actor=Actor.CLIENT, actor_id=user.id, payload={"doc_type": doc_type, "sha256": digest})
    if doc_type == "bank_statement" or content.lstrip()[:20].startswith(b"1CClientBankExchange"):
        analyze_statement(db, app, doc, content)
    db.commit()
    db.refresh(app)
    return doc


def analyze_statement(db: Session, app: Application, doc: Document, content: bytes) -> DocumentAnalysis:
    """Альфик читает выписку: очищенные обороты по месяцам, сверка с анкетой и ФНС."""
    fns = ((app.enrichment or {}).get("sources") or {}).get("fns") or {}
    declared = (app.form_data or {}).get("monthly_revenue")
    try:
        data = statement.analyze(statement.parse(content, doc.filename), float(declared) if declared else None,
                                 fns.get("annual_revenue"))
        analysis = DocumentAnalysis(kind="bank_statement", status="PARSED", data=data)
        msg = (f"Альфик разобрал выписку: {data['transactions']} операций, очищенные поступления "
               f"{data['avg_monthly_inflow']:,.0f} ₽/мес за {data['months_used']} мес.").replace(",", " ")
    except statement.StatementError as exc:
        analysis = DocumentAnalysis(kind="bank_statement", status="FAILED", error=str(exc)[:500])
        msg = f"Выписку не удалось разобрать автоматически ({exc}) — её проверит специалист"
    doc.analysis = analysis
    pipeline.log_event(db, app, "DOCUMENT_ANALYZED", msg, payload={"document_id": doc.id, "status": analysis.status})
    return analysis


latest_statement = pipeline.latest_statement


def _transition(db, app, dst, actor, actor_id, message, version, payload=None):
    try:
        pipeline.transition(db, app, dst, actor=actor, actor_id=actor_id, message=message,
                            expected_version=version, payload=payload)
    except TransitionError as exc:
        raise HTTPException(409, str(exc))
    except pipeline.ConcurrencyError as exc:
        raise HTTPException(409, str(exc))


# --- Сотрудник банка --------------------------------------------------------

def underwriter_decide(db: Session, uw: User, app: Application, req) -> Application:
    product = get_product(app.product_code)
    reason = req.reason or req.comment or ""
    if req.outcome in ("APPROVED", "COUNTER_OFFER"):
        rec = (app.decision or {}).get("recommendation") or {}
        amount = req.amount or rec.get("amount") or app.amount
        term = req.term_months or app.term_months
        rate = req.rate or rec.get("rate") or product.base_rate + 1.5
        label = "Ваши условия" if req.outcome == "APPROVED" else "Условия специалиста"
        app.offer = build_offer(product, [(int(amount), int(term), float(rate), label)],
                                ["Решение принято кредитным специалистом"] + ([req.comment] if req.comment else []))
        message = f"Решение специалиста: {LABELS[Status(req.outcome)].lower()}" + (f". {req.comment}" if req.comment else "")
    elif req.outcome == "INFO_REQUESTED":
        if not req.requested_documents:
            raise HTTPException(422, "Укажите, какие документы запросить")
        app.requested_documents = req.requested_documents
        message = "Специалист запросил документы: " + ", ".join(doc_label(d) for d in req.requested_documents)
        if req.comment:
            message += f". {req.comment}"
    else:
        message = f"Отказ: {reason}" if reason else "Отказ по решению специалиста"
    app.decision = {
        **(app.decision or {}),
        "outcome": req.outcome,
        "manual": {"by": uw.id, "by_name": uw.full_name, "at": utcnow().isoformat(), "comment": req.comment,
                   "reason": req.reason},
        "reasons": [{"code": "MANUAL", "text": reason or message, "tips": []}],
    }
    if req.outcome != "INFO_REQUESTED":
        app.decided_at = utcnow()
    app.assigned_to = uw.id
    _transition(db, app, Status(req.outcome), Actor.UNDERWRITER, uw.id, message, req.version,
                payload=req.model_dump())
    db.commit()
    return app


def ensure_company(db: Session, inn: str, name: str | None = None) -> Company:
    company = db.scalar(select(Company).where(Company.inn == inn))
    if not company:
        company = Company(inn=inn, name=name or f"Компания ИНН {inn}", legal_form="ИП" if len(inn) == 12 else "ООО")
        db.add(company)
        db.flush()
    return company
