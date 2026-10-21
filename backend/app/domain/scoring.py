"""Балльная скоринговая модель (scorecard).

Скоринг оценивает уровень риска и ничего не решает сам: решение принимает
кредитная логика (decision.py), учитывая продукт, сумму, срок и правила банка.

Каждый фактор даёт прозрачный вклад в баллы — это позволяет объяснить оценку
и клиенту (подсказки Альфика), и андеррайтеру (разбор факторов в консоли).
"""
from dataclasses import dataclass, field

BASE_SCORE = 600
MIN_SCORE, MAX_SCORE = 300, 900

INDUSTRY_RISK: dict[str, tuple[int, str]] = {
    "food": (15, "Общепит и производство продуктов — стабильный спрос"),
    "medicine": (15, "Медицина — стабильный спрос"),
    "it": (10, "ИТ и услуги — низкая доля основных средств, но стабильный рынок"),
    "manufacturing": (5, "Производство"),
    "services": (0, "Услуги"),
    "retail": (0, "Розничная торговля"),
    "agro": (-10, "Сельское хозяйство — сезонность и погодные риски"),
    "transport": (-10, "Транспорт — высокая конкуренция и зависимость от топлива"),
    "construction": (-25, "Строительство — длинные циклы оплаты, повышенный риск"),
    "other": (0, "Прочие отрасли"),
}

INDUSTRY_NAMES = {
    "food": "общепит / пищевое производство", "medicine": "медицина", "it": "ИТ", "manufacturing": "производство",
    "services": "услуги", "retail": "торговля", "agro": "сельское хозяйство", "transport": "транспорт",
    "construction": "строительство", "other": "другое",
}

RISK_CLASSES = [
    (720, "A", 0.01, "Низкий риск"),
    (650, "B", 0.025, "Умеренный риск"),
    (580, "C", 0.05, "Средний риск"),
    (500, "D", 0.10, "Повышенный риск"),
    (0, "E", 0.25, "Высокий риск"),
]


@dataclass
class ScoringInput:
    business_age_months: int
    monthly_revenue: float
    monthly_expenses: float
    existing_monthly_payments: float
    new_monthly_payment: float
    requested_amount: float
    annual_revenue_reported: float | None = None  # из ФНС
    max_delinquency_days_12m: int = 0
    delinquencies_12m: int = 0
    credit_history_months: int | None = None
    tax_arrears: float = 0.0
    industry: str = "other"
    mass_address: bool = False
    director_disqualified: bool = False
    has_collateral: bool = False
    revenue_confirmed: bool = False  # обороты подтверждены выпиской по счёту


@dataclass
class Factor:
    code: str
    name: str
    value: str
    points: int
    explanation: str
    tip: str | None = None

    @property
    def impact(self) -> str:
        return "positive" if self.points > 0 else "negative" if self.points < 0 else "neutral"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "value": self.value,
            "points": self.points,
            "impact": self.impact,
            "explanation": self.explanation,
            "tip": self.tip,
        }


@dataclass
class ScoringResult:
    score: int
    risk_class: str
    pd: float
    risk_label: str
    debt_burden: float | None
    net_cashflow: float
    factors: list[Factor] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "risk_class": self.risk_class,
            "pd": self.pd,
            "risk_label": self.risk_label,
            "debt_burden": self.debt_burden,
            "net_cashflow": round(self.net_cashflow),
            "base_score": BASE_SCORE,
            "model_version": "scorecard-1.2",
            "factors": [f.to_dict() for f in self.factors],
        }


def _money(v: float) -> str:
    return f"{v:,.0f} ₽".replace(",", " ")


def score(inp: ScoringInput) -> ScoringResult:
    factors: list[Factor] = []

    # 1. Возраст бизнеса
    age = inp.business_age_months
    if age < 6:
        pts, expl = -120, "Бизнес моложе полугода — у банка мало истории для оценки"
    elif age < 12:
        pts, expl = -60, "Бизнесу меньше года"
    elif age < 24:
        pts, expl = 0, "Бизнес работает 1–2 года"
    elif age < 60:
        pts, expl = 40, "Бизнес работает более 2 лет"
    else:
        pts, expl = 80, "Бизнес работает более 5 лет — устойчивая история"
    factors.append(Factor("business_age", "Срок работы бизнеса", f"{age} мес.", pts, expl,
                          "Через несколько месяцев работы оценка улучшится" if pts < 0 else None))

    # 2. Масштаб выручки
    annual = inp.annual_revenue_reported if inp.annual_revenue_reported is not None else inp.monthly_revenue * 12
    if annual < 3_000_000:
        pts, expl = -40, "Небольшой оборот бизнеса"
    elif annual < 12_000_000:
        pts, expl = 0, "Средний для микробизнеса оборот"
    elif annual < 60_000_000:
        pts, expl = 30, "Хороший оборот"
    else:
        pts, expl = 50, "Крупный оборот"
    factors.append(Factor("revenue", "Годовая выручка", _money(annual), pts, expl))

    # 3. Согласованность заявленной выручки и данных ФНС
    if inp.annual_revenue_reported:
        declared_annual = inp.monthly_revenue * 12
        deviation = abs(declared_annual - inp.annual_revenue_reported) / max(inp.annual_revenue_reported, 1)
        if deviation > 0.4 and inp.revenue_confirmed:
            factors.append(Factor(
                "revenue_consistency", "Сверка выручки с ФНС", f"расхождение {deviation:.0%}", 0,
                "Обороты отличаются от отчётности, но подтверждены выпиской по счёту",
            ))
        elif deviation > 0.4:
            factors.append(Factor(
                "revenue_consistency", "Сверка выручки с ФНС", f"расхождение {deviation:.0%}", -50,
                "Заявленная выручка заметно отличается от данных налоговой отчётности",
                "Приложите выписку по счёту — она подтвердит реальные обороты",
            ))
        else:
            factors.append(Factor(
                "revenue_consistency", "Сверка выручки с ФНС", f"расхождение {deviation:.0%}", 15,
                "Заявленная выручка согласуется с данными ФНС",
            ))

    # 4. Долговая нагрузка
    net_cf = inp.monthly_revenue - inp.monthly_expenses
    total_payments = inp.existing_monthly_payments + inp.new_monthly_payment
    burden: float | None = None
    if net_cf <= 0:
        pts, expl, val = -200, "Расходы не меньше выручки — нечем обслуживать кредит", "нет свободного потока"
        tip = "Проверьте анкету: укажите расходы без учёта закупок, которые финансирует кредит"
    else:
        burden = total_payments / net_cf
        val = f"{burden:.0%} свободного потока"
        tip = None
        if burden <= 0.3:
            pts, expl = 60, "Платежи по кредитам комфортны для бизнеса"
        elif burden <= 0.5:
            pts, expl = 20, "Умеренная долговая нагрузка"
        elif burden <= 0.7:
            pts, expl = -50, "Высокая долговая нагрузка"
            tip = "Уменьшите сумму или увеличьте срок — платёж станет ниже"
        else:
            pts, expl = -130, "Платежи съедают большую часть свободного потока"
            tip = "Уменьшите сумму или увеличьте срок — платёж станет ниже"
    factors.append(Factor("debt_burden", "Долговая нагрузка", val, pts, expl, tip))

    # 5. Платёжная дисциплина (БКИ)
    d = inp.max_delinquency_days_12m
    if d == 0:
        pts, expl, tip = 60, "Просрочек за последний год нет", None
    elif d <= 30:
        pts, expl, tip = -40, "Были короткие просрочки до 30 дней", "Платите вовремя ближайшие месяцы — оценка вырастет"
    elif d <= 90:
        pts, expl, tip = -150, "Были просрочки 31–90 дней", "Погасите текущие просрочки перед подачей заявки"
    else:
        pts, expl, tip = -300, "Просрочка более 90 дней", "Сначала урегулируйте просроченную задолженность"
    factors.append(Factor("delinquency", "Платёжная дисциплина", f"макс. {d} дн." if d else "без просрочек", pts, expl, tip))

    # 6. Кредитная история
    ch = inp.credit_history_months
    if ch is None or ch == 0:
        factors.append(Factor("credit_history", "Кредитная история", "нет", -10,
                              "Кредитной истории нет — банку сложнее оценить дисциплину"))
    elif ch >= 24 and d == 0:
        factors.append(Factor("credit_history", "Кредитная история", f"{ch} мес.", 30,
                              "Длинная положительная кредитная история"))
    else:
        factors.append(Factor("credit_history", "Кредитная история", f"{ch} мес.", 0, "Кредитная история есть"))

    # 7. Налоговая задолженность
    t = inp.tax_arrears
    if t <= 0:
        factors.append(Factor("tax", "Задолженность по налогам", "нет", 20, "Налоговых долгов нет"))
    elif t < 100_000:
        factors.append(Factor("tax", "Задолженность по налогам", _money(t), -30, "Есть небольшой налоговый долг",
                              "Погасите долг и приложите справку из ФНС"))
    else:
        factors.append(Factor("tax", "Задолженность по налогам", _money(t), -100, "Существенный налоговый долг",
                              "Погасите налоговую задолженность до подачи заявки"))

    # 8. Отрасль
    pts, expl = INDUSTRY_RISK.get(inp.industry, INDUSTRY_RISK["other"])
    factors.append(Factor("industry", "Отраслевой риск", INDUSTRY_NAMES.get(inp.industry, inp.industry), pts, expl))

    # 9. Соотношение суммы и оборота
    if annual > 0:
        ratio = inp.requested_amount / annual
        if ratio > 0.5:
            pts, expl = -60, "Запрошенная сумма больше половины годовой выручки"
            tip = "Рассмотрите меньшую сумму или залог"
        elif ratio > 0.3:
            pts, expl, tip = -20, "Сумма составляет заметную долю оборота", None
        else:
            pts, expl, tip = 10, "Сумма соразмерна обороту бизнеса", None
        factors.append(Factor("amount_ratio", "Сумма к годовой выручке", f"{ratio:.0%}", pts, expl, tip))

    # 10. Залог снижает риск потерь
    if inp.has_collateral:
        factors.append(Factor("collateral", "Залог", "есть", 30, "Залог снижает риск для банка"))

    # 11. Стоп-признаки из ЕГРЮЛ
    if inp.mass_address:
        factors.append(Factor("mass_address", "Адрес массовой регистрации", "да", -80,
                              "Компания зарегистрирована по адресу массовой регистрации",
                              "Подтвердите фактический адрес ведения бизнеса"))
    if inp.director_disqualified:
        factors.append(Factor("disqualified", "Дисквалификация руководителя", "да", -300,
                              "Руководитель числится в реестре дисквалифицированных лиц"))

    raw = BASE_SCORE + sum(f.points for f in factors)
    total = max(MIN_SCORE, min(MAX_SCORE, raw))
    for threshold, cls, pd, label in RISK_CLASSES:
        if total >= threshold:
            break
    return ScoringResult(
        score=total, risk_class=cls, pd=pd, risk_label=label,
        debt_burden=round(burden, 3) if burden is not None else None,
        net_cashflow=net_cf, factors=factors,
    )
