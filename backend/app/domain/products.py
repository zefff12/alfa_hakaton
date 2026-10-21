"""Каталог кредитных продуктов. Условия синтетические, для демонстрации."""
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    short: str
    description: str
    min_amount: int
    max_amount: int
    min_term: int
    max_term: int
    base_rate: float  # % годовых
    min_business_age_months: int
    collateral: str  # none | optional | required
    purposes: tuple[str, ...]
    decision_time: str
    revolving: bool = False
    required_documents: tuple[str, ...] = ()
    # Документы, которые нужны при сумме выше порога
    large_amount_threshold: int | None = None
    large_amount_documents: tuple[str, ...] = ()
    highlights: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["purposes"] = list(self.purposes)
        data["required_documents"] = list(self.required_documents)
        data["large_amount_documents"] = list(self.large_amount_documents)
        data["highlights"] = list(self.highlights)
        return data


PURPOSES: dict[str, str] = {
    "working_capital": "Пополнить оборотные средства (закупка товара, сырья)",
    "cash_gap": "Закрыть кассовый разрыв",
    "equipment": "Купить оборудование или транспорт",
    "expansion": "Открыть новую точку / запустить направление",
    "contract": "Исполнить госконтракт или тендер",
    "renovation": "Ремонт и модернизация помещения",
    "refinance": "Рефинансировать кредит в другом банке",
    "other": "Другая цель",
}

DOCUMENT_TYPES: dict[str, str] = {
    "bank_statement": "Выписка по расчётному счёту за 6 месяцев",
    "financial_statements": "Бухгалтерская отчётность за последний год",
    "equipment_offer": "Коммерческое предложение / договор поставки оборудования",
    "state_contract": "Госконтракт или протокол победы в тендере",
    "tax_certificate": "Справка об исполнении обязанности по уплате налогов",
    "collateral_docs": "Документы на залоговое имущество",
    "loan_agreement": "Кредитный договор в другом банке (для рефинансирования)",
    "other": "Другой документ",
}

PRODUCTS: dict[str, Product] = {
    p.code: p
    for p in [
        Product(
            code="EXPRESS",
            name="Экспресс-кредит без залога",
            short="Быстрые деньги на любые цели",
            description="Небольшая сумма без залога и поручителей. Решение онлайн, минимум документов.",
            min_amount=100_000,
            max_amount=5_000_000,
            min_term=3,
            max_term=36,
            base_rate=24.0,
            min_business_age_months=6,
            collateral="none",
            purposes=("working_capital", "cash_gap", "renovation", "expansion", "other"),
            decision_time="от 15 минут",
            highlights=("Без залога", "Решение онлайн", "Досрочное погашение без комиссии"),
        ),
        Product(
            code="WORKING",
            name="Кредит на пополнение оборотных средств",
            short="Закупка товара, сырья, сезонные запасы",
            description="Для регулярных закупок и подготовки к сезону. Можно уменьшить ставку, предоставив залог.",
            min_amount=500_000,
            max_amount=30_000_000,
            min_term=6,
            max_term=36,
            base_rate=21.0,
            min_business_age_months=12,
            collateral="optional",
            purposes=("working_capital", "cash_gap", "refinance"),
            decision_time="1–2 рабочих дня",
            large_amount_threshold=5_000_000,
            large_amount_documents=("bank_statement",),
            highlights=("Ставка ниже с залогом", "Отсрочка платежа по телу до 3 мес."),
        ),
        Product(
            code="INVEST",
            name="Инвестиционный кредит",
            short="Оборудование, транспорт, развитие",
            description="Длинные деньги на покупку оборудования и развитие бизнеса. Залогом выступает приобретаемое имущество.",
            min_amount=1_000_000,
            max_amount=100_000_000,
            min_term=12,
            max_term=84,
            base_rate=19.0,
            min_business_age_months=12,
            collateral="required",
            purposes=("equipment", "expansion", "renovation"),
            decision_time="3–5 рабочих дней",
            required_documents=("equipment_offer",),
            large_amount_threshold=10_000_000,
            large_amount_documents=("financial_statements",),
            highlights=("Срок до 7 лет", "Залог — приобретаемое имущество"),
        ),
        Product(
            code="OVERDRAFT",
            name="Овердрафт к расчётному счёту",
            short="Подушка на случай кассовых разрывов",
            description="Возобновляемый лимит на счёте: платите проценты только за дни использования.",
            min_amount=100_000,
            max_amount=10_000_000,
            min_term=12,
            max_term=12,
            base_rate=23.0,
            min_business_age_months=6,
            collateral="none",
            purposes=("cash_gap", "working_capital"),
            decision_time="от 1 часа",
            revolving=True,
            highlights=("Проценты только за использованные дни", "Лимит восстанавливается"),
        ),
        Product(
            code="TENDER",
            name="Кредит на исполнение госконтракта",
            short="Финансирование под 44-ФЗ / 223-ФЗ",
            description="Деньги на исполнение контракта, погашение — из оплаты заказчика.",
            min_amount=500_000,
            max_amount=50_000_000,
            min_term=3,
            max_term=24,
            base_rate=20.0,
            min_business_age_months=12,
            collateral="none",
            purposes=("contract",),
            decision_time="1–3 рабочих дня",
            required_documents=("state_contract",),
            highlights=("Погашение из выручки по контракту", "Без залога"),
        ),
    ]
}


def get_product(code: str | None) -> Product | None:
    return PRODUCTS.get(code or "")


def required_documents_for(product: Product, amount: int | None, purpose: str | None) -> list[str]:
    docs = list(product.required_documents)
    if product.large_amount_threshold and amount and amount > product.large_amount_threshold:
        docs.extend(d for d in product.large_amount_documents if d not in docs)
    if purpose == "refinance" and "loan_agreement" not in docs:
        docs.append("loan_agreement")
    return docs
