"""Машина состояний кредитной заявки.

Все переходы описаны явно: попытка перевести заявку в недопустимый статус —
ошибка домена, а не тихое изменение данных.
"""
from enum import StrEnum


class Status(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    DATA_CHECK = "DATA_CHECK"
    ENRICHMENT = "ENRICHMENT"
    SCORING = "SCORING"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    INFO_REQUESTED = "INFO_REQUESTED"
    APPROVED = "APPROVED"
    COUNTER_OFFER = "COUNTER_OFFER"
    REJECTED = "REJECTED"
    SIGNING = "SIGNING"
    ISSUING = "ISSUING"
    DISBURSED = "DISBURSED"
    CANCELLED = "CANCELLED"


class Actor(StrEnum):
    CLIENT = "client"
    SYSTEM = "system"
    UNDERWRITER = "underwriter"


S, A = Status, Actor

# (из статуса, в статус) -> кто может выполнить переход
TRANSITIONS: dict[tuple[Status, Status], set[Actor]] = {
    (S.DRAFT, S.SUBMITTED): {A.CLIENT},
    (S.SUBMITTED, S.DATA_CHECK): {A.SYSTEM},
    (S.DATA_CHECK, S.ENRICHMENT): {A.SYSTEM},
    (S.DATA_CHECK, S.INFO_REQUESTED): {A.SYSTEM},
    (S.ENRICHMENT, S.SCORING): {A.SYSTEM},
    (S.ENRICHMENT, S.MANUAL_REVIEW): {A.SYSTEM},
    (S.ENRICHMENT, S.REJECTED): {A.SYSTEM},
    (S.SCORING, S.APPROVED): {A.SYSTEM},
    (S.SCORING, S.COUNTER_OFFER): {A.SYSTEM},
    (S.SCORING, S.INFO_REQUESTED): {A.SYSTEM},
    (S.SCORING, S.MANUAL_REVIEW): {A.SYSTEM},
    (S.SCORING, S.REJECTED): {A.SYSTEM},
    (S.MANUAL_REVIEW, S.APPROVED): {A.UNDERWRITER},
    (S.MANUAL_REVIEW, S.COUNTER_OFFER): {A.UNDERWRITER},
    (S.MANUAL_REVIEW, S.INFO_REQUESTED): {A.UNDERWRITER},
    (S.MANUAL_REVIEW, S.REJECTED): {A.UNDERWRITER},
    (S.INFO_REQUESTED, S.SUBMITTED): {A.CLIENT},
    (S.APPROVED, S.SIGNING): {A.CLIENT},
    (S.COUNTER_OFFER, S.SIGNING): {A.CLIENT},
    (S.SIGNING, S.ISSUING): {A.CLIENT},
    (S.ISSUING, S.DISBURSED): {A.SYSTEM},
    # Отмена клиентом возможна до подписания
    (S.DRAFT, S.CANCELLED): {A.CLIENT},
    (S.INFO_REQUESTED, S.CANCELLED): {A.CLIENT},
    (S.MANUAL_REVIEW, S.CANCELLED): {A.CLIENT},
    (S.APPROVED, S.CANCELLED): {A.CLIENT},
    (S.COUNTER_OFFER, S.CANCELLED): {A.CLIENT},
    (S.SIGNING, S.CANCELLED): {A.CLIENT},
}

# Статусы, которые обрабатывает воркер конвейера автоматически
AUTOMATED: set[Status] = {S.SUBMITTED, S.DATA_CHECK, S.ENRICHMENT, S.SCORING, S.ISSUING}
FINAL: set[Status] = {S.DISBURSED, S.REJECTED, S.CANCELLED}
EDITABLE: set[Status] = {S.DRAFT}

LABELS: dict[Status, str] = {
    S.DRAFT: "Черновик",
    S.SUBMITTED: "Заявка отправлена",
    S.DATA_CHECK: "Проверка данных",
    S.ENRICHMENT: "Запрос сведений ЕГРЮЛ, ФНС, БКИ",
    S.SCORING: "Оценка и решение",
    S.MANUAL_REVIEW: "Рассматривает специалист",
    S.INFO_REQUESTED: "Нужны дополнительные данные",
    S.APPROVED: "Одобрено",
    S.COUNTER_OFFER: "Предложены другие условия",
    S.REJECTED: "Отказ",
    S.SIGNING: "Подписание договора",
    S.ISSUING: "Выдача средств",
    S.DISBURSED: "Средства выданы",
    S.CANCELLED: "Отменена",
}


class TransitionError(Exception):
    pass


def can_transition(src: Status | str, dst: Status | str, actor: Actor | str) -> bool:
    allowed = TRANSITIONS.get((Status(src), Status(dst)))
    return bool(allowed) and Actor(actor) in allowed


def ensure_transition(src: Status | str, dst: Status | str, actor: Actor | str) -> None:
    if not can_transition(src, dst, actor):
        raise TransitionError(
            f"Переход {src} → {dst} недоступен для роли «{actor}»"
        )


def allowed_targets(src: Status | str, actor: Actor | str) -> list[str]:
    return [dst.value for (s, dst), actors in TRANSITIONS.items() if s == Status(src) and Actor(actor) in actors]
