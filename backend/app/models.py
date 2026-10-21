"""Модель данных кредитного конвейера."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    """Клиент банка — юрлицо или ИП. Хранит данные анкеты и подтверждённые реквизиты."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    inn: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    ogrn: Mapped[str | None] = mapped_column(String(15))
    name: Mapped[str] = mapped_column(String(255))
    legal_form: Mapped[str] = mapped_column(String(10), default="ООО")  # ООО / ИП / АО
    okved: Mapped[str | None] = mapped_column(String(16))
    okved_name: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(32))  # укрупнённая отрасль для ленты и риска
    region: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(255))
    director: Mapped[str | None] = mapped_column(String(255))
    registered_at: Mapped[str | None] = mapped_column(String(10))  # ISO-дата из ЕГРЮЛ
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="company")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # client | underwriter
    full_name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(128))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    demo_hint: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company | None] = relationship(back_populates="users")


class Application(Base):
    """Кредитная заявка — центральный объект конвейера."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), index=True, default="DRAFT")
    # Оптимистическая блокировка: защищает от гонок при параллельной обработке
    version: Mapped[int] = mapped_column(Integer, default=1)

    product_code: Mapped[str | None] = mapped_column(String(32))
    purpose: Mapped[str | None] = mapped_column(String(64))
    purpose_comment: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[int | None] = mapped_column(Integer)
    term_months: Mapped[int | None] = mapped_column(Integer)
    has_collateral: Mapped[bool] = mapped_column(Boolean, default=False)
    collateral_description: Mapped[str | None] = mapped_column(String(255))

    # Анкета: финансы со слов клиента
    form_data: Mapped[dict] = mapped_column(JSON, default=dict)
    consents: Mapped[dict] = mapped_column(JSON, default=dict)
    # Результаты этапов конвейера
    precheck: Mapped[dict | None] = mapped_column(JSON)
    data_check: Mapped[dict | None] = mapped_column(JSON)
    enrichment: Mapped[dict | None] = mapped_column(JSON)
    scoring: Mapped[dict | None] = mapped_column(JSON)
    decision: Mapped[dict | None] = mapped_column(JSON)
    offer: Mapped[dict | None] = mapped_column(JSON)
    requested_documents: Mapped[list] = mapped_column(JSON, default=list)
    signing: Mapped[dict | None] = mapped_column(JSON)
    loan: Mapped[dict | None] = mapped_column(JSON)

    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship()
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", order_by="ApplicationEvent.id", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="application", order_by="Document.id", cascade="all, delete-orphan"
    )


class ApplicationEvent(Base):
    """Журнал аудита: каждое изменение статуса и значимое действие участника."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    actor_type: Mapped[str] = mapped_column(String(16))  # client | system | underwriter
    actor_id: Mapped[int | None] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application] = relationship(back_populates="events")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(48))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="UPLOADED")  # UPLOADED | ACCEPTED | REJECTED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[Application] = relationship(back_populates="documents")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    """История диалога с ассистентом Альфиком (сохраняется между сессиями)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(16))  # rules | llm
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedInteraction(Base):
    """Реакции на ленту — сигнал для персонализации."""

    __tablename__ = "feed_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))  # open | hide | like
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
