"""Кредитная логика: превращает оценку риска в решение и условия.

Одинаковый скоринговый балл может приводить к разным решениям для разных
продуктов, сумм и сроков: здесь применяются стоп-правила, полномочия
автоматического решения, расчёт лимита по платёжеспособности и подбор
альтернативных условий (контрпредложение).
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.domain import calculator
from app.domain.products import PRODUCTS, Product
from app.domain.scoring import ScoringInput, ScoringResult

RATE_PREMIUM = {"A": 0.0, "B": 1.5, "C": 3.0, "D": 5.0, "E": 8.0}
COLLATERAL_DISCOUNT = 2.0
# Доля свободного денежного потока, которую можно направить на все кредиты
MAX_BURDEN = 0.5
UNSECURED_REVENUE_CAP = 0.5
SECURED_REVENUE_CAP = 1.0
OVERDRAFT_REVENUE_CAP = 0.5  # от среднемесячной выручки


@dataclass
class Rule:
    code: str
    name: str
    result: str  # pass | fail | warn
    detail: str

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name, "result": self.result, "detail": self.detail}


@dataclass
class Decision:
    outcome: str  # APPROVED | COUNTER_OFFER | INFO_REQUESTED | MANUAL_REVIEW | REJECTED
    reasons: list[dict] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    offer: dict | None = None
    requested_documents: list[str] = field(default_factory=list)
    limit: int | None = None
    recommendation: dict | None = None  # подсказка андеррайтеру при ручном рассмотрении

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "reasons": self.reasons,
            "rules": [r.to_dict() for r in self.rules],
            "offer": self.offer,
            "requested_documents": self.requested_documents,
            "limit": self.limit,
            "recommendation": self.recommendation,
            "engine_version": "rules-1.3",
        }


def offer_rate(product: Product, risk_class: str, has_collateral: bool) -> float:
    rate = product.base_rate + RATE_PREMIUM.get(risk_class, 8.0)
    if has_collateral and product.collateral == "optional":
        rate -= COLLATERAL_DISCOUNT
    return round(rate, 2)


def capacity_limit(product: Product, inp: ScoringInput, rate: float, term: int) -> int:
    """Максимальная сумма по платёжеспособности и обороту."""
    net_cf = inp.monthly_revenue - inp.monthly_expenses
    available = MAX_BURDEN * net_cf - inp.existing_monthly_payments
    if available <= 0:
        return 0
    annual = inp.annual_revenue_reported or inp.monthly_revenue * 12
    if product.revolving:
        by_capacity = available / (rate / 100 / 12)
        by_revenue = OVERDRAFT_REVENUE_CAP * annual / 12
    else:
        by_capacity = calculator.max_amount_for_payment(available, rate, term)
        cap = SECURED_REVENUE_CAP if inp.has_collateral else UNSECURED_REVENUE_CAP
        by_revenue = cap * annual
    return calculator.round_amount(min(product.max_amount, by_capacity, by_revenue))


def build_offer(product: Product, options: list[tuple[int, int, float, str]], conditions: list[str]) -> dict:
    opts = []
    for i, (amount, term, rate, label) in enumerate(options):
        calc = calculator.summary(amount, rate, term, product.revolving)
        opts.append({"id": f"opt{i + 1}", "label": label, "product_code": product.code, **calc})
    return {
        "product_code": product.code,
        "product_name": product.name,
        "options": opts,
        "conditions": conditions,
        "valid_until": (date.today() + timedelta(days=30)).isoformat(),
    }


def _alternative_product(current: Product, inp: ScoringInput, purpose: str | None) -> Product | None:
    candidates = [
        p for p in PRODUCTS.values()
        if p.code != current.code
        and p.min_business_age_months <= inp.business_age_months
        and (purpose in p.purposes or "other" in p.purposes)
        and (p.collateral != "required" or inp.has_collateral)
    ]
    candidates.sort(key=lambda p: p.base_rate)
    return candidates[0] if candidates else None


def decide(
    product: Product,
    inp: ScoringInput,
    result: ScoringResult,
    *,
    term: int,
    purpose: str | None,
    egrul_status: str = "ACTIVE",
    provided_documents: set[str] | None = None,
    auto_decision_limit: int = 10_000_000,
) -> Decision:
    provided = provided_documents or set()
    rules: list[Rule] = []
    amount = int(inp.requested_amount)

    def stop(code: str, text: str, tips: list[str] | None = None) -> Decision:
        return Decision(outcome="REJECTED", reasons=[{"code": code, "text": text, "tips": tips or []}], rules=rules)

    # --- Стоп-факторы -------------------------------------------------------
    active = egrul_status == "ACTIVE"
    rules.append(Rule("KO_STATUS", "Компания действующая (ЕГРЮЛ/ЕГРИП)", "pass" if active else "fail",
                      f"Статус: {egrul_status}"))
    if not active:
        return stop("KO_STATUS", "По данным ЕГРЮЛ компания находится в процессе ликвидации или не действует")

    rules.append(Rule("KO_DISQ", "Руководитель не дисквалифицирован", "fail" if inp.director_disqualified else "pass", ""))
    if inp.director_disqualified:
        return stop("KO_DISQ", "Руководитель компании числится в реестре дисквалифицированных лиц")

    serious_overdue = inp.max_delinquency_days_12m > 90
    rules.append(Rule("KO_OVERDUE", "Нет просрочек > 90 дней за 12 мес.", "fail" if serious_overdue else "pass",
                      f"Максимальная просрочка: {inp.max_delinquency_days_12m} дн."))
    if serious_overdue:
        return stop("KO_OVERDUE", "В кредитной истории есть просрочка более 90 дней за последний год",
                    ["Урегулируйте просроченную задолженность", "Повторная заявка возможна через 6 месяцев без новых просрочек"])

    net_cf = inp.monthly_revenue - inp.monthly_expenses
    rules.append(Rule("KO_CASHFLOW", "Положительный денежный поток", "pass" if net_cf > 0 else "fail",
                      f"Выручка − расходы = {net_cf:,.0f} ₽/мес".replace(",", " ")))
    if net_cf <= 0:
        return stop("KO_CASHFLOW", "Расходы бизнеса не меньше выручки — нет средств для обслуживания кредита",
                    ["Проверьте, верно ли указаны выручка и расходы в анкете"])

    rules.append(Rule("KO_CLASS", "Класс риска не ниже D", "fail" if result.risk_class == "E" else "pass",
                      f"Класс {result.risk_class}, балл {result.score}"))
    if result.risk_class == "E":
        negative = sorted((f for f in result.factors if f.points < 0), key=lambda f: f.points)[:3]
        return stop("KO_CLASS", "Совокупная оценка риска не позволяет одобрить кредит сейчас",
                    [f.tip for f in negative if f.tip])

    # --- Соответствие продукту ---------------------------------------------
    age_ok = inp.business_age_months >= product.min_business_age_months
    rules.append(Rule("PRODUCT_AGE", f"Срок работы ≥ {product.min_business_age_months} мес.", "pass" if age_ok else "fail",
                      f"Факт: {inp.business_age_months} мес."))
    collateral_ok = product.collateral != "required" or inp.has_collateral
    rules.append(Rule("PRODUCT_COLLATERAL", "Требование к залогу", "pass" if collateral_ok else "fail",
                      "Залог обязателен" if product.collateral == "required" else "Залог не обязателен"))

    if not age_ok or not collateral_ok:
        alt = _alternative_product(product, inp, purpose)
        if not alt:
            return stop("PRODUCT_FIT", f"Бизнес пока не подходит под требования продукта «{product.name}»",
                        [f"Минимальный срок работы — {product.min_business_age_months} мес."])
        alt_rate = offer_rate(alt, result.risk_class, inp.has_collateral)
        alt_term = min(max(term, alt.min_term), alt.max_term)
        alt_limit = capacity_limit(alt, inp, alt_rate, alt_term)
        alt_amount = min(amount, alt_limit)
        if alt_amount < alt.min_amount:
            return stop("PRODUCT_FIT", "Не удалось подобрать продукт под параметры бизнеса")
        offer = build_offer(alt, [(alt_amount, alt_term, alt_rate, f"{alt.name}")],
                            ["Продукт подобран вместо исходного: бизнес не прошёл требования к сроку работы или залогу"])
        return Decision(
            outcome="COUNTER_OFFER",
            reasons=[{"code": "ALT_PRODUCT", "text": f"Вместо «{product.name}» предлагаем «{alt.name}»", "tips": []}],
            rules=rules, offer=offer, limit=alt_limit,
        )

    # --- Достаточность документов ------------------------------------------
    need_docs: list[str] = []
    if inp.annual_revenue_reported:
        deviation = abs(inp.monthly_revenue * 12 - inp.annual_revenue_reported) / inp.annual_revenue_reported
        dev_ok = deviation <= 0.4 or "bank_statement" in provided
        rules.append(Rule("DOC_REVENUE", "Выручка подтверждена", "pass" if dev_ok else "warn",
                          f"Расхождение с ФНС {deviation:.0%}"))
        if not dev_ok:
            need_docs.append("bank_statement")
    if 0 < inp.tax_arrears < 100_000:
        tax_ok = "tax_certificate" in provided
        rules.append(Rule("DOC_TAX", "Налоговый долг погашен", "pass" if tax_ok else "warn",
                          f"Долг по данным ФНС: {inp.tax_arrears:,.0f} ₽".replace(",", " ")))
        if not tax_ok:
            need_docs.append("tax_certificate")
    if need_docs:
        return Decision(
            outcome="INFO_REQUESTED",
            reasons=[{"code": "NEED_DOCS", "text": "Чтобы завершить оценку, нужно подтвердить данные документами", "tips": []}],
            rules=rules, requested_documents=need_docs,
        )

    rate = offer_rate(product, result.risk_class, inp.has_collateral)
    limit = capacity_limit(product, inp, rate, term)
    rules.append(Rule("LIMIT", "Сумма в пределах лимита платёжеспособности",
                      "pass" if amount <= limit else "warn",
                      f"Лимит {limit:,.0f} ₽ при сроке {term} мес.".replace(",", " ")))

    recommendation = {"amount": min(amount, limit), "term_months": term, "rate": rate, "limit": limit}

    # --- Полномочия автоматического решения --------------------------------
    manual_reasons = []
    if amount > auto_decision_limit:
        manual_reasons.append(f"Сумма выше лимита автоматического решения ({auto_decision_limit:,.0f} ₽)".replace(",", " "))
    if result.risk_class == "D":
        manual_reasons.append("Повышенный риск (класс D) — нужна экспертная оценка")
    if result.risk_class == "C" and amount > 3_000_000:
        manual_reasons.append("Средний риск при сумме более 3 млн ₽")
    if inp.mass_address:
        manual_reasons.append("Адрес массовой регистрации")
    if inp.tax_arrears >= 100_000:
        manual_reasons.append("Существенная налоговая задолженность")
    rules.append(Rule("AUTHORITY", "Решение в полномочиях автоматики", "warn" if manual_reasons else "pass",
                      "; ".join(manual_reasons) or "Да"))
    if manual_reasons:
        return Decision(
            outcome="MANUAL_REVIEW",
            reasons=[{"code": "MANUAL", "text": r, "tips": []} for r in manual_reasons],
            rules=rules, limit=limit, recommendation=recommendation,
        )

    conditions = ["Без комиссии за досрочное погашение", "Ежемесячный аннуитетный платёж"]
    if product.revolving:
        conditions = ["Проценты начисляются только на использованную сумму", "Лимит восстанавливается после погашения"]
    if inp.has_collateral and product.collateral != "none":
        conditions.append("Залог оформляется при подписании договора")

    if amount <= limit:
        offer = build_offer(product, [(amount, term, rate, "Ваши условия")], conditions)
        return Decision(outcome="APPROVED", reasons=[{"code": "OK", "text": "Заявка соответствует требованиям банка", "tips": []}],
                        rules=rules, offer=offer, limit=limit)

    # --- Контрпредложение --------------------------------------------------
    options: list[tuple[int, int, float, str]] = []
    if not product.revolving:
        for longer in range(term + 1, product.max_term + 1):
            if capacity_limit(product, inp, rate, longer) >= amount:
                options.append((amount, longer, rate, f"Та же сумма на {longer} мес."))
                break
        else:
            long_limit = capacity_limit(product, inp, rate, product.max_term)
            if product.max_term > term and long_limit > limit and long_limit >= product.min_amount:
                options.append((long_limit, product.max_term, rate, f"Больше денег на {product.max_term} мес."))
    if limit >= product.min_amount:
        options.append((limit, term, rate, f"Меньшая сумма на {term} мес."))
    if not options:
        return stop("LIMIT", "Текущая платёжеспособность бизнеса не позволяет обслуживать кредит в этом продукте",
                     ["Снизьте текущую долговую нагрузку", "Рассмотрите меньшую сумму"])
    offer = build_offer(product, options, conditions)
    return Decision(
        outcome="COUNTER_OFFER",
        reasons=[{"code": "LIMIT", "text": "Запрошенная сумма выше комфортной долговой нагрузки — предлагаем безопасные условия", "tips": []}],
        rules=rules, offer=offer, limit=limit, recommendation=recommendation,
    )
