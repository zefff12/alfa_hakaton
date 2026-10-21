"""«Каковы мои шансы на одобрение?» — предварительная оценка готовности к подаче.

Работает только на данных со слов клиента, без запроса в БКИ (согласия ещё нет).
Использует ту же скоринговую модель, что и банк, поэтому подсказки честные:
клиент видит, какие факторы влияют на решение, и что можно улучшить.
Это ориентир, а не обещание одобрения.
"""
from dataclasses import dataclass

from app.domain import calculator
from app.domain.decision import capacity_limit, offer_rate
from app.domain.products import Product
from app.domain.scoring import ScoringInput, score

DELINQUENCY_ANSWERS = {"none": 0, "minor": 15, "serious": 60, "current": 120}

DISCLAIMER = (
    "Это предварительный ориентир на основе ваших ответов, а не решение банка и не обещание одобрения. "
    "Итоговое решение принимается после проверки данных и кредитной истории."
)


@dataclass
class PrecheckAnswers:
    product: Product
    amount: int
    term_months: int
    business_age_months: int
    monthly_revenue: float
    monthly_expenses: float
    existing_monthly_payments: float
    delinquency: str = "none"
    tax_arrears: bool = False
    has_collateral: bool = False
    industry: str = "other"


def evaluate(a: PrecheckAnswers) -> dict:
    rate_guess = offer_rate(a.product, "B", a.has_collateral)
    new_payment = calculator.summary(a.amount, rate_guess, a.term_months, a.product.revolving)["monthly_payment"]
    inp = ScoringInput(
        business_age_months=a.business_age_months,
        monthly_revenue=a.monthly_revenue,
        monthly_expenses=a.monthly_expenses,
        existing_monthly_payments=a.existing_monthly_payments,
        new_monthly_payment=new_payment,
        requested_amount=a.amount,
        max_delinquency_days_12m=DELINQUENCY_ANSWERS.get(a.delinquency, 0),
        credit_history_months=24 if a.existing_monthly_payments > 0 else None,
        tax_arrears=50_000 if a.tax_arrears else 0,
        industry=a.industry,
        has_collateral=a.has_collateral,
    )
    res = score(inp)
    # Нормируем балл в шкалу «готовности» 0–100
    readiness = max(0, min(100, round((res.score - 420) / (780 - 420) * 100)))
    if a.delinquency == "current" or res.net_cashflow <= 0:
        readiness = min(readiness, 15)

    limit = capacity_limit(a.product, inp, rate_guess, a.term_months)
    blockers = []
    if a.business_age_months < a.product.min_business_age_months:
        blockers.append(f"Для продукта нужен срок работы бизнеса от {a.product.min_business_age_months} мес.")
        readiness = min(readiness, 30)
    if a.product.collateral == "required" and not a.has_collateral:
        blockers.append("Для этого продукта нужен залог (например, приобретаемое оборудование)")
        readiness = min(readiness, 35)
    if a.amount > a.product.max_amount or a.amount < a.product.min_amount:
        blockers.append(
            f"Сумма должна быть от {a.product.min_amount:,} до {a.product.max_amount:,} ₽".replace(",", " ")
        )

    if readiness >= 70:
        level, title = "high", "Высокая готовность"
    elif readiness >= 45:
        level, title = "medium", "Средняя готовность"
    else:
        level, title = "low", "Низкая готовность"

    tips = [f.tip for f in sorted(res.factors, key=lambda f: f.points) if f.tip and f.points < 0][:3]
    suggestion = None
    if limit and a.amount > limit:
        longer = None
        if not a.product.revolving:
            for t in range(a.term_months + 1, a.product.max_term + 1):
                if capacity_limit(a.product, inp, rate_guess, t) >= a.amount:
                    longer = t
                    break
        suggestion = {
            "comfortable_amount": limit,
            "longer_term": longer,
            "text": (
                f"Комфортная сумма при сроке {a.term_months} мес. — до {limit:,.0f} ₽".replace(",", " ")
                + (f", либо та же сумма на {longer} мес." if longer else "")
            ),
        }

    return {
        "readiness": readiness,
        "level": level,
        "title": title,
        "estimated_rate": rate_guess,
        "estimated_payment": new_payment,
        "estimated_limit": limit,
        "blockers": blockers,
        "tips": tips,
        "suggestion": suggestion,
        "factors": [f.to_dict() for f in res.factors],
        "disclaimer": DISCLAIMER,
    }
