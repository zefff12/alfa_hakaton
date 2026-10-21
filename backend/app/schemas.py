"""Схемы запросов и ответов API (контракты для OpenAPI)."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    login: str = Field(examples=["kolosok"])
    password: str = Field(examples=["demo"])


class RegisterRequest(BaseModel):
    login: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=4, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    position: str | None = Field(default=None, max_length=128)
    inn: str = Field(pattern=r"^(\d{10}|\d{12})$", description="ИНН компании (10 цифр) или ИП (12 цифр)")


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    inn: str
    ogrn: str | None
    name: str
    legal_form: str
    okved: str | None
    okved_name: str | None
    industry: str | None
    region: str | None
    address: str | None
    director: str | None
    registered_at: str | None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    login: str
    role: Literal["client", "underwriter"]
    full_name: str
    position: str | None
    company: CompanyOut | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DemoAccount(BaseModel):
    login: str
    password: str
    role: str
    full_name: str
    company: str | None
    hint: str | None


class ApplicationCreate(BaseModel):
    product_code: str | None = Field(default=None, examples=["WORKING"])
    purpose: str | None = Field(default=None, examples=["working_capital"])
    amount: int | None = Field(default=None, ge=0, examples=[3_000_000])
    term_months: int | None = Field(default=None, ge=1, le=120, examples=[24])
    form_data: dict[str, Any] | None = None
    precheck: dict[str, Any] | None = None


class ApplicationUpdate(BaseModel):
    """Частичное обновление черновика (автосохранение)."""
    version: int | None = Field(default=None, description="Версия для оптимистической блокировки")
    product_code: str | None = None
    purpose: str | None = None
    purpose_comment: str | None = Field(default=None, max_length=2000)
    amount: int | None = Field(default=None, ge=0)
    term_months: int | None = Field(default=None, ge=1, le=120)
    has_collateral: bool | None = None
    collateral_description: str | None = Field(default=None, max_length=255)
    form_data: dict[str, Any] | None = None
    consents: dict[str, Any] | None = None


class ApplicationAction(BaseModel):
    version: int | None = None
    comment: str | None = Field(default=None, max_length=2000)


class AcceptOfferRequest(BaseModel):
    version: int | None = None
    option_id: str = Field(examples=["opt1"])


class SignRequest(BaseModel):
    version: int | None = None
    code: str = Field(pattern=r"^\d{6}$")


class UnderwriterDecisionRequest(BaseModel):
    version: int | None = None
    outcome: Literal["APPROVED", "COUNTER_OFFER", "INFO_REQUESTED", "REJECTED"]
    amount: int | None = Field(default=None, ge=0)
    term_months: int | None = Field(default=None, ge=1, le=120)
    rate: float | None = Field(default=None, ge=0, le=100)
    requested_documents: list[str] = Field(default_factory=list)
    reason: str | None = Field(default=None, max_length=500)
    comment: str | None = Field(default=None, max_length=2000)


class PrecheckRequest(BaseModel):
    product_code: str = Field(examples=["EXPRESS"])
    amount: int = Field(ge=0, examples=[1_500_000])
    term_months: int = Field(ge=1, le=120, examples=[18])
    business_age_months: int = Field(ge=0, le=1200, examples=[30])
    monthly_revenue: float = Field(ge=0, examples=[900_000])
    monthly_expenses: float = Field(ge=0, examples=[600_000])
    existing_monthly_payments: float = Field(default=0, ge=0)
    delinquency: Literal["none", "minor", "serious", "current"] = "none"
    tax_arrears: bool = False
    has_collateral: bool = False


class AdvisorRequest(BaseModel):
    purpose: str = Field(examples=["equipment"])
    amount: int = Field(ge=0, examples=[4_000_000])
    term_months: int | None = Field(default=None, ge=1, le=120)
    business_age_months: int = Field(default=24, ge=0)
    has_collateral: bool = False
    urgency: Literal["urgent", "normal"] = "normal"
    monthly_revenue: float | None = Field(default=None, ge=0)


class CalcRequest(BaseModel):
    product_code: str
    amount: int = Field(ge=0)
    term_months: int = Field(ge=1, le=120)
    has_collateral: bool = False
    comfortable_payment: float | None = Field(default=None, ge=0, description="Комфортный платёж — для подбора условий")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    application_id: int | None = None
    page: str | None = Field(default=None, description="Экран, с которого задан вопрос — для контекста")


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    source: str | None
    meta: dict | None
    created_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    application_id: int | None
    title: str
    body: str
    is_read: bool
    created_at: datetime


class FeedReaction(BaseModel):
    item_id: str
    action: Literal["open", "hide", "like"]


class EgrulLookupOut(BaseModel):
    inn: str
    name: str | None = None
    data: dict[str, Any]
