"""Разбор свободного рассказа предпринимателя в параметры кредитной заявки.

Клиент пишет или говорит своими словами: «нужно 2 млн на новую печь, верну за
3 года, выручка около 600 тысяч в месяц». Детерминированный парсер (правила +
словари) извлекает сумму, срок, цель, финансы, залог и срочность и для каждого
значения запоминает фрагмент текста, из которого оно получено, — это
показывается клиенту, чтобы он мог проверить, что Альфик понял правильно.

Правила работают без GPU и предсказуемо на числах; LLM (если включена)
только дополняет поля, которые правила не нашли (см. services/intake.py).
"""
import re
from dataclasses import dataclass, field
from datetime import date

FIELD_LABELS = {
    "purpose": "Цель",
    "amount": "Сумма кредита",
    "term_months": "Срок",
    "monthly_revenue": "Выручка в месяц",
    "monthly_expenses": "Расходы в месяц",
    "existing_payments": "Платежи по текущим кредитам",
    "comfortable_payment": "Комфортный платёж",
    "has_collateral": "Залог",
    "collateral_description": "Что в залоге",
    "business_age_months": "Возраст бизнеса",
    "urgency": "Срочность",
}

MONEY_FIELDS = ("amount", "monthly_revenue", "monthly_expenses", "existing_payments", "comfortable_payment")

PURPOSE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("refinance", (r"рефинанс", r"перекредит", r"погасить кредит в друг", r"закрыть кредит в друг")),
    ("contract", (r"тендер", r"госконтракт", r"госзаказ", r"44-фз", r"223-фз", r"контракт с заказчик",
                  r"исполнени\w* контракт")),
    ("cash_gap", (r"кассов\w* разрыв", r"зарплат", r"отсрочк\w* оплат", r"не хватает денег до", r"пока заказчик")),
    ("equipment", (r"оборудован", r"печь", r"печи", r"станок", r"станк", r"линию", r"машин", r"автомобил",
                   r"грузовик", r"фургон", r"трактор", r"кофемашин", r"холодильник", r"техник", r"аппарат")),
    ("expansion", (r"открыть\w* нов", r"новую точку", r"новую торгов", r"второй магазин", r"филиал",
                   r"новое направлен", r"расширени", r"масштабир", r"запустить")),
    ("renovation", (r"ремонт", r"модерниз", r"переобору", r"отделк")),
    ("working_capital", (r"закупк", r"закупить", r"товар", r"сырь", r"материал", r"запас", r"сезон", r"оборотк",
                         r"оборотн")),
]

COLLATERAL_OBJECTS = {
    r"недвижимост": "недвижимость", r"помещени": "коммерческое помещение", r"квартир": "квартира",
    r"склад": "склад", r"здани": "здание", r"оборудовани": "оборудование", r"автомобил": "автомобиль",
    r"машин": "автомобиль", r"печь": "приобретаемая печь", r"станок": "станок", r"техник": "техника",
    r"транспорт": "транспорт", r"земл": "земельный участок",
}

_WORD_NUM = {
    "один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
    "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "полтора": 1.5, "полторы": 1.5, "двадцать": 20,
    "тридцать": 30, "сто": 100, "двести": 200, "триста": 300, "пятьсот": 500,
}
_UNITS = r"(млрд|миллиард\w*|млн|миллион\w*|лям\w*|тыс\w*|тысяч\w*|т\.?\s?р\.?|к(?=\s|$)|руб\w*|₽|р\.)"
_NUM = r"(\d{1,3}(?: \d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
MONEY_RE = re.compile(_NUM + r"\s*" + _UNITS + "?")
NEED_RE = re.compile(r"нужн|хочу|взять|кредит на|займ|получить|не хватает|требуется")


@dataclass
class Extracted:
    field: str
    value: object
    source: str
    confidence: float = 0.9
    via: str = "rules"

    def to_dict(self) -> dict:
        return {"field": self.field, "label": FIELD_LABELS[self.field], "value": self.value,
                "display": display(self.field, self.value), "source": self.source,
                "confidence": self.confidence, "via": self.via}


@dataclass
class IntakeResult:
    items: list[Extracted] = field(default_factory=list)

    def get(self, name: str):
        return next((i for i in self.items if i.field == name), None)

    def add(self, item: Extracted) -> None:
        if not self.get(item.field):
            self.items.append(item)


def display(field_name: str, value) -> str:
    if value is None:
        return "—"
    if field_name in MONEY_FIELDS:
        return f"{float(value):,.0f} ₽".replace(",", " ")
    if field_name == "term_months":
        n = int(value)
        if n >= 12 and n % 12 == 0:
            y = n // 12
            return f"{y} {'год' if y == 1 else 'года' if y < 5 else 'лет'} ({n} мес.)"
        return f"{n} мес."
    if field_name == "business_age_months":
        years, months = divmod(int(value), 12)
        parts = ([f"{years} г."] if years else []) + ([f"{months} мес."] if months else [])
        return " ".join(parts) or "меньше месяца"
    if field_name == "has_collateral":
        return "есть" if value else "нет"
    if field_name == "urgency":
        return "срочно" if value == "urgent" else "можно подождать"
    if field_name == "purpose":
        from app.domain.products import PURPOSES
        return PURPOSES.get(value, value)
    return str(value)


def normalize(text: str) -> str:
    t = text.lower().replace("ё", "е").replace(" ", " ").replace(" ", " ")
    t = re.sub(r"пол\s?-?миллиона", "500 тысяч", t)
    t = re.sub(r"\bпол\s?года\b", "6 месяцев", t)
    t = re.sub(r"\bполтора года\b", "18 месяцев", t)
    t = re.sub(r"\bпар[уы]\s+(лет|года)\b", "2 года", t)
    for word, num in sorted(_WORD_NUM.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(rf"\b{word}\b(?=\s+(млн|миллион|тысяч|тыс|года|год|лет|месяц|мес))", str(num), t)
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)  # «2,5 млн» — запятая как десятичный разделитель
    return t


def _to_rub(num: str, unit: str | None) -> float | None:
    try:
        value = float(num.replace(" ", ""))
    except ValueError:
        return None
    u = (unit or "").lower()
    if u.startswith(("млрд", "миллиард")):
        return value * 1e9
    if u.startswith(("млн", "миллион", "лям")):
        return value * 1e6
    if u.startswith(("тыс", "т")) or u == "к":
        return value * 1e3
    return value


def _clauses(t: str) -> list[str]:
    """Фрагменты-факты: запятые, точки (кроме десятичных), союзы «а / но / плюс»."""
    parts = re.split(r"[;!?\n,]+|(?<!\d)\.|\.(?!\d)|\s(?:а|но|плюс|при этом)\s", t)
    return [p.strip(" -—") for p in parts if p and p.strip(" -—")]


def parse(text: str, today: date | None = None) -> IntakeResult:
    today = today or date.today()
    t = normalize(text)
    clauses = _clauses(t)
    res = IntakeResult()

    # --- Возраст бизнеса (раньше срока: «работаем 5 лет» — не срок кредита) ----
    for clause in clauses:
        m = re.search(r"(?:работа\w*|существу\w*|на рынке|бизнесу|компании|фирме)\D{0,25}?(?<!\d)(\d{1,2}(?:\.\d+)?)\s*(год\w*|лет|месяц\w*|мес)", clause)
        if m:
            n = float(m.group(1))
            res.add(Extracted("business_age_months", int(n * 12 if m.group(2)[0] in "гл" else n), clause))
            break
        m = re.search(r"(?:работа\w*|открыл\w*|основ\w*|зарегистр\w*|начал\w*)\D{0,15}(?:с|в)\s+((?:19|20)\d{2})", clause)
        if m and 1990 <= int(m.group(1)) <= today.year:
            res.add(Extracted("business_age_months", max(1, (today.year - int(m.group(1))) * 12), clause, 0.7))
            break

    # --- Срок кредита --------------------------------------------------------
    term_re = re.compile(r"(?:на|за|в течение|срок\w*|верн\w*(?:\s+(?:за|через))?)\s*(\d+(?:\.\d+)?)?\s*(год\w*|лет|месяц\w*|мес)\b")
    for clause in clauses:
        if re.search(r"работа\w*|существу\w*|на рынке|бизнесу|открыл", clause):
            continue
        m = term_re.search(clause)
        if m:
            n = float(m.group(1)) if m.group(1) else 1.0
            months = n * 12 if m.group(2)[0] in "гл" else n
            if 1 <= months <= 120:
                res.add(Extracted("term_months", int(round(months)), clause))
                break

    # --- Деньги: классифицируем по контексту своего фрагмента ---------------
    unassigned: list[tuple[float, str, bool]] = []
    for clause in clauses:
        masked = re.sub(r"\d+(?:\.\d+)?\s*(год\w*|лет|месяц\w*|мес)\b", " ", clause)  # сроки
        masked = re.sub(r"\b(?:19|20)\d{2}\b(?!\s*" + _UNITS + ")", " ", masked)     # годы
        masked = re.sub(r"\d+(?:\.\d+)?\s*%", " ", masked)                               # проценты
        for m in MONEY_RE.finditer(masked):
            value = _to_rub(m.group(1), m.group(2))
            if value is None:
                continue
            before = masked[: m.start()]
            if not m.group(2) and value < 1000:
                if re.search(r"выручк|оборот|расход|плач|платеж|кредит|нужн|займ|сумм|тысяч", masked):
                    value *= 1000  # «выручка 600», «нужно тысяч 300» — говорят в тысячах
                else:
                    continue
            yearly = bool(re.search(r"в год|за год|годов", masked))

            if re.search(r"комфорт|не больше|не более|максимум|потяну|платить (могу|готов)|готов\w* плат", masked):
                res.add(Extracted("comfortable_payment", value, clause))
            elif re.search(r"плач\w*|платеж\w* по|ежемесячн\w* платеж|уже есть кредит|текущ\w* кредит|лизинг", masked) \
                    and not NEED_RE.search(before):
                res.add(Extracted("existing_payments", round(value / 12) if yearly else value, clause))
            elif re.search(r"выручк|оборот|зарабатыва|доход|приход|продаж|поступлен|выруча", masked):
                res.add(Extracted("monthly_revenue", round(value / 12) if yearly else value, clause, 0.8 if yearly else 0.9))
            elif re.search(r"расход|трат|затрат|издерж", masked):
                res.add(Extracted("monthly_expenses", round(value / 12) if yearly else value, clause))
            else:
                unassigned.append((value, clause, bool(NEED_RE.search(before))))

    # Сумма кредита: сначала суммы после «нужно / хочу взять», затем первая свободная
    candidates = sorted((u for u in unassigned if u[0] >= 10_000), key=lambda u: not u[2])
    if candidates:
        value, clause, need = candidates[0]
        res.add(Extracted("amount", int(value), clause, 0.9 if need else 0.7))

    # --- Цель ---------------------------------------------------------------
    for code, patterns in PURPOSE_KEYWORDS:
        clause = next((c for c in clauses for p in patterns if re.search(p, c)), None)
        if clause:
            res.add(Extracted("purpose", code, clause, 0.8))
            break

    # --- Залог --------------------------------------------------------------
    if re.search(r"без залог|залога нет|нет залог|нечего (в )?залож", t):
        res.add(Extracted("has_collateral", False, "без залога"))
    else:
        clause = next((c for c in clauses if re.search(r"залог\w*|в обеспечени\w*|заложить", c)), None)
        if clause:
            res.add(Extracted("has_collateral", True, clause))
            idx = clauses.index(clause)
            around = " ".join(clauses[idx: idx + 2])
            obj = next((label for stem, label in COLLATERAL_OBJECTS.items() if re.search(stem, around)), None)
            if obj:
                res.add(Extracted("collateral_description", obj, around, 0.7))

    # --- Срочность ----------------------------------------------------------
    m = re.search(r"не срочно|не горит|могу подождать", t)
    if m:
        res.add(Extracted("urgency", "normal", m.group(0)))
    else:
        m = re.search(r"срочно|как можно быстрее|побыстрее|сегодня|завтра|до конца недели|горит", t)
        if m:
            res.add(Extracted("urgency", "urgent", m.group(0)))

    return res
