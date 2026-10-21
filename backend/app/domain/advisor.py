"""Подбор кредитного продукта под задачу бизнеса (логика Альфика-консультанта).

Правила прозрачны: для каждого продукта считается степень соответствия
и объяснение «почему подходит / почему нет» простым языком.
"""
from dataclasses import dataclass

from app.domain import calculator
from app.domain.products import PRODUCTS, PURPOSES


@dataclass
class NeedProfile:
    purpose: str
    amount: int
    term_months: int | None = None
    business_age_months: int = 24
    has_collateral: bool = False
    urgency: str = "normal"  # urgent | normal
    monthly_revenue: float | None = None


def recommend(need: NeedProfile) -> dict:
    results = []
    for p in PRODUCTS.values():
        score = 50
        pros: list[str] = []
        cons: list[str] = []

        if need.purpose in p.purposes:
            score += 30
            pros.append(f"Подходит для цели «{PURPOSES.get(need.purpose, need.purpose).lower()}»")
            if "other" not in p.purposes:
                score += 5  # специализированный продукт под задачу обычно дешевле универсального
        elif "other" in p.purposes:
            score += 5
            pros.append("Можно потратить на любые цели бизнеса")
        else:
            score -= 40
            cons.append("Продукт предназначен для других целей")

        if p.min_amount <= need.amount <= p.max_amount:
            score += 10
        elif need.amount > p.max_amount:
            score -= 30
            cons.append(f"Максимальная сумма — {p.max_amount:,} ₽".replace(",", " "))
        else:
            score -= 20
            cons.append(f"Минимальная сумма — {p.min_amount:,} ₽".replace(",", " "))

        if need.business_age_months < p.min_business_age_months:
            score -= 40
            cons.append(f"Нужен бизнес старше {p.min_business_age_months} мес.")

        if p.collateral == "required" and not need.has_collateral:
            score -= 25
            cons.append("Нужен залог (часто — само приобретаемое имущество)")
        elif p.collateral == "optional" and need.has_collateral:
            score += 5
            pros.append("С залогом ставка будет ниже")
        elif p.collateral == "none":
            pros.append("Без залога")

        if need.urgency == "urgent":
            if "минут" in p.decision_time or "час" in p.decision_time:
                score += 10
                pros.append(f"Быстрое решение: {p.decision_time}")
            elif "5" in p.decision_time:
                score -= 10
                cons.append(f"Рассмотрение дольше: {p.decision_time}")

        term = need.term_months or min(max(12, p.min_term), p.max_term)
        if need.term_months and not (p.min_term <= need.term_months <= p.max_term):
            score -= 10
            cons.append(f"Срок {p.min_term} мес." if p.min_term == p.max_term else f"Срок {p.min_term}–{p.max_term} мес.")
            term = min(max(need.term_months, p.min_term), p.max_term)

        amount = min(max(need.amount, p.min_amount), p.max_amount)
        estimate = calculator.summary(amount, p.base_rate, term, p.revolving)

        if need.monthly_revenue and estimate["monthly_payment"] > need.monthly_revenue * 0.3:
            score -= 10
            cons.append("Платёж больше 30% месячной выручки — подумайте о большем сроке")

        results.append({
            "product": p.to_dict(),
            "fit_score": max(0, min(100, score)),
            "pros": pros,
            "cons": cons,
            "estimate": estimate,
        })

    results.sort(key=lambda r: (r["fit_score"], -r["product"]["base_rate"]), reverse=True)
    best = results[0]
    suitable = [r for r in results if r["fit_score"] >= 60]
    explanation = (
        f"Под вашу задачу лучше всего подходит «{best['product']['name']}». "
        + ("; ".join(best["pros"][:2]) + "." if best["pros"] else "")
    ) if best["fit_score"] >= 60 else (
        "Ни один продукт не подходит идеально — посмотрите варианты ниже или задайте вопрос мне в чате."
    )
    return {"best": best["product"]["code"] if suitable else None, "explanation": explanation, "items": results}
