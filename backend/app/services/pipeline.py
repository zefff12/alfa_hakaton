"""Кредитный конвейер: переходы статусов, аудит и автоматические этапы обработки."""
import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import calculator
from app.domain.decision import decide
from app.domain.products import DOCUMENT_TYPES, get_product, required_documents_for
from app.domain.scoring import ScoringInput, score
from app.domain.state_machine import AUTOMATED, Actor, Status, ensure_transition
from app.integrations import clients
from app.models import Application, ApplicationEvent, Notification, utcnow
from app.services.alfik_texts import NOTIFY

log = logging.getLogger("pipeline")


class ConcurrencyError(Exception):
    pass


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def log_event(db: Session, app: Application, event_type: str, message: str, *, actor: Actor = Actor.SYSTEM,
              actor_id: int | None = None, payload: dict | None = None,
              from_status: str | None = None, to_status: str | None = None) -> None:
    db.add(ApplicationEvent(
        application_id=app.id, from_status=from_status, to_status=to_status, actor_type=actor.value,
        actor_id=actor_id, event_type=event_type, message=message, payload=payload,
    ))


def transition(db: Session, app: Application, dst: Status, *, actor: Actor, actor_id: int | None = None,
               message: str = "", payload: dict | None = None, expected_version: int | None = None) -> None:
    """Единственная точка смены статуса: проверка правил, версия, аудит, уведомление."""
    src = Status(app.status)
    ensure_transition(src, dst, actor)
    if expected_version is not None and expected_version != app.version:
        raise ConcurrencyError("Заявка была изменена другим участником. Обновите страницу.")
    app.status = dst.value
    app.version += 1
    app.updated_at = utcnow()
    app.next_run_at = utcnow() + timedelta(seconds=get_settings().pipeline_step_delay_s) if dst in AUTOMATED else None
    app.attempts = 0
    log_event(db, app, "STATUS_CHANGED", message or f"{src} → {dst}", actor=actor, actor_id=actor_id,
              payload=payload, from_status=src.value, to_status=dst.value)
    if dst in NOTIFY:
        db.add(Notification(user_id=app.user_id, application_id=app.id,
                            title=NOTIFY[dst].format(number=app.number), body=message or ""))
    log.info("transition app=%s %s->%s actor=%s", app.number, src, dst, actor)


def provided_doc_types(app: Application) -> set[str]:
    return {d.doc_type for d in app.documents if d.status != "REJECTED"}


def latest_statement(app: Application) -> dict | None:
    """Последняя успешно разобранная выписка по заявке."""
    for d in reversed(app.documents):
        if d.analysis and d.analysis.status == "PARSED" and d.status != "REJECTED":
            return {**d.analysis.data, "document_id": d.id, "filename": d.filename}
    return None


def business_age_months(registered_at: str | None) -> int:
    if not registered_at:
        return 0
    reg = date.fromisoformat(registered_at)
    today = date.today()
    return max(0, (today.year - reg.year) * 12 + today.month - reg.month - (1 if today.day < reg.day else 0))


# --- Этапы -------------------------------------------------------------------

def _stage_intake(db: Session, app: Application) -> None:
    transition(db, app, Status.DATA_CHECK, actor=Actor.SYSTEM, message="Заявка принята в обработку")


def _stage_data_check(db: Session, app: Application) -> None:
    product = get_product(app.product_code)
    issues: list[str] = []
    fd = app.form_data or {}
    if not product:
        issues.append("Не выбран кредитный продукт")
    else:
        if not app.amount or not (product.min_amount <= app.amount <= product.max_amount):
            issues.append("Сумма вне диапазона продукта")
        if not app.term_months or not (product.min_term <= app.term_months <= product.max_term):
            issues.append("Срок вне диапазона продукта")
    for key, label in (("monthly_revenue", "среднемесячная выручка"), ("monthly_expenses", "среднемесячные расходы")):
        if fd.get(key) in (None, ""):
            issues.append(f"Не указана {label}")
    if not (app.consents or {}).get("bki"):
        issues.append("Нет согласия на запрос кредитной истории")

    missing_docs = []
    if product:
        provided = provided_doc_types(app)
        missing_docs = [d for d in required_documents_for(product, app.amount, app.purpose) if d not in provided]

    app.data_check = {"checked_at": utcnow().isoformat(), "issues": issues, "missing_documents": missing_docs,
                      "ok": not issues and not missing_docs}
    if issues or missing_docs:
        app.requested_documents = missing_docs
        text = "; ".join(issues + [DOCUMENT_TYPES[d] for d in missing_docs])
        transition(db, app, Status.INFO_REQUESTED, actor=Actor.SYSTEM,
                   message=f"Не хватает данных: {text}", payload=app.data_check)
    else:
        transition(db, app, Status.ENRICHMENT, actor=Actor.SYSTEM, message="Данные заявки полные и корректные")


def _stage_enrichment(db: Session, app: Application) -> None:
    inn = app.company.inn
    result: dict = {"requested_at": utcnow().isoformat(), "sources": {}, "errors": []}
    consent_id = (app.consents or {}).get("bki_consent_id") or f"CNS-{uuid.uuid4().hex[:10]}"
    for name, call in (("egrul", lambda: clients.fetch_egrul(inn)),
                       ("fns", lambda: clients.fetch_fns(inn)),
                       ("bki", lambda: clients.fetch_bki(inn, consent_id))):
        try:
            result["sources"][name] = call()
        except clients.IntegrationError as exc:
            result["errors"].append({"source": name, "service": exc.service, "message": exc.message})
            log_event(db, app, "INTEGRATION_ERROR", f"{exc.service}: {exc.message}", payload={"source": name})
    app.enrichment = result

    egrul = result["sources"].get("egrul")
    if egrul:
        # Нормализация: подтверждённые реквизиты из ЕГРЮЛ заменяют введённые вручную
        c = app.company
        c.name = egrul.get("name") or c.name
        c.ogrn, c.okved, c.okved_name = egrul.get("ogrn"), egrul.get("okved"), egrul.get("okved_name")
        c.industry, c.region, c.address = egrul.get("industry"), egrul.get("region"), egrul.get("address")
        c.director, c.registered_at = egrul.get("director"), egrul.get("registered_at")
        c.legal_form = egrul.get("legal_form") or c.legal_form

    if result["errors"]:
        failed = ", ".join(e["service"] for e in result["errors"])
        transition(db, app, Status.MANUAL_REVIEW, actor=Actor.SYSTEM,
                   message=f"Не удалось получить данные: {failed}. Заявка передана специалисту",
                   payload={"errors": result["errors"]})
        return
    if egrul and egrul.get("status") != "ACTIVE":
        app.decision = {"outcome": "REJECTED", "reasons": [{
            "code": "KO_STATUS", "text": "По данным ЕГРЮЛ компания в процессе ликвидации или не действует", "tips": []}],
            "rules": [{"code": "KO_STATUS", "name": "Компания действующая", "result": "fail",
                       "detail": f"Статус: {egrul.get('status')}"}], "engine_version": "rules-1.3"}
        app.decided_at = utcnow()
        transition(db, app, Status.REJECTED, actor=Actor.SYSTEM, message="Стоп-фактор: статус компании в ЕГРЮЛ")
        return
    transition(db, app, Status.SCORING, actor=Actor.SYSTEM, message="Сведения ЕГРЮЛ, ФНС и БКИ получены")


def build_scoring_input(app: Application) -> ScoringInput:
    product = get_product(app.product_code)
    fd = app.form_data or {}
    src = (app.enrichment or {}).get("sources", {})
    egrul, fns, bki = src.get("egrul", {}), src.get("fns", {}), src.get("bki", {})
    rate_guess = product.base_rate + 1.5
    new_payment = calculator.summary(app.amount, rate_guess, app.term_months, product.revolving)["monthly_payment"]
    existing = max(float(fd.get("existing_payments") or 0), float(bki.get("total_monthly_payments") or 0))
    declared = float(fd.get("monthly_revenue") or 0)
    stmt = latest_statement(app)
    revenue, confirmed = declared, "bank_statement" in provided_doc_types(app)
    if stmt and stmt.get("avg_monthly_inflow"):
        # Выписка разобрана: подтверждаем обороты фактом, при завышении — считаем по выписке (консервативно)
        confirmed = True
        if stmt["avg_monthly_inflow"] < declared * 0.85:
            revenue = float(stmt["avg_monthly_inflow"])
    return ScoringInput(
        business_age_months=business_age_months(egrul.get("registered_at") or app.company.registered_at),
        monthly_revenue=revenue,
        monthly_expenses=float(fd.get("monthly_expenses") or 0),
        existing_monthly_payments=existing,
        new_monthly_payment=new_payment,
        requested_amount=float(app.amount),
        annual_revenue_reported=fns.get("annual_revenue"),
        max_delinquency_days_12m=int(bki.get("max_delinquency_days_12m") or 0),
        delinquencies_12m=int(bki.get("delinquencies_12m") or 0),
        credit_history_months=bki.get("credit_history_months"),
        tax_arrears=float(fns.get("tax_arrears") or 0),
        industry=egrul.get("industry") or app.company.industry or "other",
        mass_address=bool(egrul.get("mass_address")),
        director_disqualified=bool(egrul.get("director_disqualified")),
        has_collateral=bool(app.has_collateral),
        revenue_confirmed=confirmed,
    )


def _stage_scoring(db: Session, app: Application) -> None:
    product = get_product(app.product_code)
    inp = build_scoring_input(app)
    res = score(inp)
    app.scoring = {**res.to_dict(), "input": inp.__dict__, "scored_at": utcnow().isoformat()}
    egrul = (app.enrichment or {}).get("sources", {}).get("egrul", {})
    d = decide(product, inp, res, term=app.term_months, purpose=app.purpose,
               egrul_status=egrul.get("status", "ACTIVE"), provided_documents=provided_doc_types(app),
               auto_decision_limit=get_settings().auto_decision_limit)
    app.decision = d.to_dict()
    app.offer = d.offer
    if d.outcome == "INFO_REQUESTED":
        app.requested_documents = d.requested_documents
    if d.outcome in ("APPROVED", "COUNTER_OFFER", "REJECTED"):
        app.decided_at = utcnow()
    message = d.reasons[0]["text"] if d.reasons else ""
    transition(db, app, Status(d.outcome), actor=Actor.SYSTEM, message=message,
               payload={"score": res.score, "risk_class": res.risk_class, "outcome": d.outcome})


def _stage_issuing(db: Session, app: Application) -> None:
    offer = app.offer or {}
    chosen = next((o for o in offer.get("options", []) if o["id"] == (app.signing or {}).get("option_id")), None)
    chosen = chosen or (offer.get("options") or [{}])[0]
    product = get_product(chosen.get("product_code") or app.product_code)
    start = date.today()
    app.loan = {
        "contract_number": f"КД-{app.number}",
        "account": "40702810" + secrets.token_hex(6)[:12].upper().replace("A", "1").replace("B", "2")
                   .replace("C", "3").replace("D", "4").replace("E", "5").replace("F", "6"),
        "product_code": product.code,
        "product_name": product.name,
        "amount": chosen.get("amount"),
        "rate": chosen.get("rate"),
        "term_months": chosen.get("term_months"),
        "monthly_payment": chosen.get("monthly_payment"),
        "disbursed_at": utcnow().isoformat(),
        "revolving": product.revolving,
        "schedule": [] if product.revolving else calculator.schedule(chosen["amount"], chosen["rate"], chosen["term_months"], start),
    }
    transition(db, app, Status.DISBURSED, actor=Actor.SYSTEM,
               message=f"Средства {chosen.get('amount'):,} ₽ перечислены на расчётный счёт".replace(",", " "))


STAGES = {
    Status.SUBMITTED: _stage_intake,
    Status.DATA_CHECK: _stage_data_check,
    Status.ENRICHMENT: _stage_enrichment,
    Status.SCORING: _stage_scoring,
    Status.ISSUING: _stage_issuing,
}


def process_step(db: Session, app: Application) -> bool:
    """Выполнить один автоматический этап. Возвращает True, если статус изменился."""
    handler = STAGES.get(Status(app.status))
    if not handler:
        return False
    try:
        handler(db, app)
        db.commit()
        return True
    except Exception:  # noqa: BLE001 — этап не должен ронять воркер
        db.rollback()
        log.exception("stage_failed app=%s status=%s", app.number, app.status)
        app = db.get(Application, app.id)
        app.attempts += 1
        app.next_run_at = utcnow() + timedelta(seconds=5 * app.attempts)
        if app.attempts >= 3 and Status(app.status) in (Status.DATA_CHECK, Status.ENRICHMENT, Status.SCORING):
            log_event(db, app, "STAGE_FAILED", "Этап не выполнен после 3 попыток, передано специалисту",
                      from_status=app.status, to_status=Status.MANUAL_REVIEW.value)
            app.status = Status.MANUAL_REVIEW.value
            app.next_run_at = None
            app.version += 1
        db.commit()
        return False


def run_due(db: Session, limit: int = 20) -> int:
    """Обработать заявки, у которых наступило время следующего шага."""
    now = utcnow()
    stmt = (
        select(Application)
        .where(Application.status.in_([s.value for s in AUTOMATED]))
        .where(Application.next_run_at <= now)
        .order_by(Application.next_run_at)
        .limit(limit)
    )
    if db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    apps = list(db.scalars(stmt))
    done = 0
    for app in apps:
        if _aware(app.next_run_at) and _aware(app.next_run_at) <= now:
            done += int(process_step(db, app))
    return done


def drain(db: Session, app_id: int, max_steps: int = 10) -> Application:
    """Прогнать заявку по автоматическим этапам синхронно (для тестов и демо-режима)."""
    for _ in range(max_steps):
        app = db.get(Application, app_id)
        db.refresh(app)
        if Status(app.status) not in AUTOMATED:
            return app
        process_step(db, app)
    return db.get(Application, app_id)


def generate_signing_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"
