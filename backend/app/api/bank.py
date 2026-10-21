"""API консоли кредитного специалиста (андеррайтера)."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.state_machine import AUTOMATED, LABELS, Actor, Status
from app.models import Application, ApplicationEvent, Document, User
from app.schemas import ApplicationAction, UnderwriterDecisionRequest
from app.security import require_underwriter
from app.services import applications as svc
from app.services import pipeline

router = APIRouter(prefix="/api/bank", tags=["Консоль банка"])

QUEUES = {
    "manual": [Status.MANUAL_REVIEW],
    "waiting_client": [Status.INFO_REQUESTED, Status.APPROVED, Status.COUNTER_OFFER, Status.SIGNING],
    "processing": list(AUTOMATED),
    "done": [Status.DISBURSED, Status.REJECTED, Status.CANCELLED],
}


def _row(a: Application) -> dict:
    scoring = a.scoring or {}
    return {
        "id": a.id, "number": a.number, "status": a.status, "status_label": LABELS[Status(a.status)],
        "company": a.company.name, "inn": a.company.inn, "product_code": a.product_code, "amount": a.amount,
        "term_months": a.term_months, "score": scoring.get("score"), "risk_class": scoring.get("risk_class"),
        "outcome": (a.decision or {}).get("outcome"), "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None, "assigned_to": a.assigned_to,
        "manual_reasons": [r["text"] for r in (a.decision or {}).get("reasons", [])] if a.status == "MANUAL_REVIEW" else [],
    }


@router.get("/applications", summary="Очередь заявок")
def queue(queue: str | None = Query(default=None, description="manual | waiting_client | processing | done"),
          q: str | None = Query(default=None, description="Поиск по номеру, ИНН или названию"),
          uw: User = Depends(require_underwriter), db: Session = Depends(get_db)):
    stmt = select(Application).where(Application.status != Status.DRAFT.value).order_by(Application.updated_at.desc())
    if queue in QUEUES:
        stmt = stmt.where(Application.status.in_([s.value for s in QUEUES[queue]]))
    rows = [_row(a) for a in db.scalars(stmt).all()]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["number"].lower() or ql in r["inn"] or ql in r["company"].lower()]
    return rows


@router.get("/metrics", summary="Метрики конвейера")
def metrics(uw: User = Depends(require_underwriter), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.status != Status.DRAFT.value)).all()
    by_status = Counter(a.status for a in apps)
    decided = [a for a in apps if a.decided_at and a.submitted_at]
    durations = [(a.decided_at - a.submitted_at).total_seconds() for a in decided
                 if a.decided_at.tzinfo == a.submitted_at.tzinfo]
    outcomes = Counter((a.decision or {}).get("outcome") for a in apps if a.decision)
    manual = sum(1 for a in apps if (a.decision or {}).get("manual"))
    positive = outcomes.get("APPROVED", 0) + outcomes.get("COUNTER_OFFER", 0)
    final_outcomes = positive + outcomes.get("REJECTED", 0)
    return {
        "total": len(apps),
        "by_status": [{"status": s, "label": LABELS[Status(s)], "count": c} for s, c in by_status.most_common()],
        "manual_queue": by_status.get("MANUAL_REVIEW", 0),
        "approval_rate": round(positive / final_outcomes, 3) if final_outcomes else None,
        "auto_decision_share": round(1 - manual / len(decided), 3) if decided else None,
        "avg_decision_seconds": round(sum(durations) / len(durations)) if durations else None,
        "disbursed_amount": sum((a.loan or {}).get("amount") or 0 for a in apps if a.status == "DISBURSED"),
    }


@router.get("/applications/{app_id}", summary="Полная карточка заявки для специалиста")
def detail(app_id: int, uw: User = Depends(require_underwriter), db: Session = Depends(get_db)):
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Заявка не найдена")
    return svc.serialize(app, for_bank=True)


@router.post("/applications/{app_id}/assign", summary="Взять заявку в работу")
def assign(app_id: int, req: ApplicationAction, uw: User = Depends(require_underwriter), db: Session = Depends(get_db)):
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Заявка не найдена")
    app.assigned_to = uw.id
    pipeline.log_event(db, app, "ASSIGNED", f"Заявку взял в работу {uw.full_name}", actor=Actor.UNDERWRITER, actor_id=uw.id)
    db.commit()
    return svc.serialize(app, for_bank=True)


@router.post("/applications/{app_id}/decision", summary="Решение специалиста по заявке")
def decision(app_id: int, req: UnderwriterDecisionRequest, uw: User = Depends(require_underwriter),
             db: Session = Depends(get_db)):
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Заявка не найдена")
    return svc.serialize(svc.underwriter_decide(db, uw, app, req), for_bank=True)


@router.post("/documents/{doc_id}/review", summary="Принять или отклонить документ")
def review_document(doc_id: int, status: str = Query(pattern="^(ACCEPTED|REJECTED)$"),
                    uw: User = Depends(require_underwriter), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    doc.status = status
    pipeline.log_event(db, doc.application, "DOCUMENT_REVIEWED",
                       f"Документ «{svc.doc_label(doc.doc_type)}»: {'принят' if status == 'ACCEPTED' else 'отклонён'}",
                       actor=Actor.UNDERWRITER, actor_id=uw.id)
    db.commit()
    return svc.serialize(doc.application, for_bank=True)


@router.get("/audit", summary="Журнал событий конвейера")
def audit(limit: int = Query(default=100, le=500), uw: User = Depends(require_underwriter), db: Session = Depends(get_db)):
    events = db.scalars(select(ApplicationEvent).order_by(ApplicationEvent.id.desc()).limit(limit)).all()
    return [{"id": e.id, "application_id": e.application_id, "number": e.application.number, "event_type": e.event_type,
             "from_status": e.from_status, "to_status": e.to_status, "actor_type": e.actor_type, "message": e.message,
             "created_at": e.created_at.isoformat()} for e in events]
