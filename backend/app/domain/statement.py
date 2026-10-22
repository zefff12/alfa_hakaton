"""Разбор банковской выписки: «очищенные» обороты по месяцам и концентрация покупателей.

Поддерживаемые форматы:
* 1С «Клиент-Банк» (1CClientBankExchange) — стандартная выгрузка любого банка РФ, обычно в windows-1251;
* CSV из интернет-банка: колонки даты, прихода/расхода (или знаковой суммы), контрагента и назначения.

Как и в банковской практике, из поступлений исключаются переводы между своими
счетами и полученные займы/кредиты — они не являются выручкой.
"""
import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

NOT_REVENUE = re.compile(r"собствен\w* средств|перевод\w* (с|со|между) (своего|собствен\w*|сво\w*) счет|"
                         r"выдач\w* кредит|предоставлен\w* (кредит|займ)|по договору займа|займ\w* от учредит|"
                         r"возврат депозит|пополнение депозит|кредитн\w* средств", re.IGNORECASE)


# Эквайринг и наличная выручка — это множество розничных покупателей, а не один контрагент
RETAIL = re.compile(r"эквайринг|розничн\w* выручк|инкассац|наличн\w* выручк", re.IGNORECASE)


class StatementError(ValueError):
    pass


@dataclass
class Tx:
    day: date
    amount: float  # >0 — поступление, <0 — списание
    counterparty: str = ""
    purpose: str = ""
    excluded: str | None = None  # причина исключения из выручки


@dataclass
class Parsed:
    fmt: str
    account: str | None = None
    owner: str | None = None
    txs: list[Tx] = field(default_factory=list)


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise StatementError("Не удалось прочитать кодировку файла")


def _date(s: str) -> date | None:
    s = s.strip()
    for f in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(s[:10], f).date()
        except ValueError:
            continue
    return None


def _num(s: str | None) -> float:
    if not s:
        return 0.0
    s = s.replace(" ", "").replace(" ", "").replace(",", ".")
    s = re.sub(r"[^\d.\-+]", "", s)
    try:
        return float(s) if s not in ("", "-", "+", ".") else 0.0
    except ValueError:
        return 0.0


def parse_1c(text: str) -> Parsed:
    if not text.lstrip().startswith("1CClientBankExchange"):
        raise StatementError("Это не файл обмена 1С")
    own = None
    m = re.search(r"^РасчСчет=(\d{20})", text, re.MULTILINE)
    if m:
        own = m.group(1)
    p = Parsed("1c", account=own)
    for block in re.findall(r"СекцияДокумент=.*?КонецДокумента", text, re.DOTALL):
        f = dict(re.findall(r"^([^=\r\n]+)=(.*?)\r?$", block, re.MULTILINE))
        amount = _num(f.get("Сумма"))
        if not amount:
            continue
        payer_acc, payee_acc = f.get("ПлательщикСчет", ""), f.get("ПолучательСчет", "")
        incoming = (own and payee_acc == own) or (not own and f.get("ДатаПоступило"))
        day = _date(f.get("ДатаПоступило") or f.get("ДатаСписано") or f.get("Дата", ""))
        if not day:
            continue
        cp = (f.get("Плательщик1") or f.get("Плательщик") or "") if incoming else (f.get("Получатель1") or f.get("Получатель") or "")
        tx = Tx(day, amount if incoming else -amount, cp.strip(), f.get("НазначениеПлатежа", "").strip())
        if incoming and own and payer_acc and f.get("ПлательщикИНН") and f.get("ПлательщикИНН") == f.get("ПолучательИНН"):
            tx.excluded = "перевод между своими счетами"
        p.txs.append(tx)
    if not p.txs:
        raise StatementError("В файле 1С не найдено операций")
    return p


def parse_csv(text: str) -> Parsed:
    sample = text[:4000]
    delim = ";" if sample.count(";") >= sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    header_idx = next((i for i, r in enumerate(rows[:15]) if any(re.search(r"дата", c, re.I) for c in r)), None)
    if header_idx is None:
        raise StatementError("Не найдена строка заголовков (колонка «Дата»)")
    head = [c.strip().lower() for c in rows[header_idx]]

    def col(*patterns: str) -> int | None:
        return next((i for i, c in enumerate(head) for p in patterns if re.search(p, c)), None)

    c_date = col(r"^дата( операции| проводки)?$", r"дата")
    c_in = col(r"приход", r"поступ", r"кредит", r"зачисл")
    c_out = col(r"расход", r"списан", r"дебет")
    c_sum = col(r"^сумма", r"сумма операции")
    c_cp = col(r"контрагент", r"плательщик|получатель", r"корреспондент")
    c_pur = col(r"назначени", r"описани", r"комментар")
    if c_date is None or (c_sum is None and c_in is None):
        raise StatementError("Не найдены колонки с датой и суммой")
    p = Parsed("csv")
    for r in rows[header_idx + 1:]:
        if len(r) <= c_date:
            continue
        day = _date(r[c_date])
        if not day:
            continue
        if c_in is not None:
            inflow = _num(r[c_in]) if c_in < len(r) else 0
            outflow = _num(r[c_out]) if c_out is not None and c_out < len(r) else 0
            amount = inflow - abs(outflow)
        else:
            amount = _num(r[c_sum])
        if not amount:
            continue
        p.txs.append(Tx(day, amount, r[c_cp].strip() if c_cp is not None and c_cp < len(r) else "",
                        r[c_pur].strip() if c_pur is not None and c_pur < len(r) else ""))
    if not p.txs:
        raise StatementError("В CSV не найдено операций")
    return p


def parse(content: bytes, filename: str = "") -> Parsed:
    text = _decode(content)
    if text.lstrip().startswith("1CClientBankExchange"):
        return parse_1c(text)
    if filename.lower().endswith((".csv", ".txt")) or text.count(";") > 5 or text.count(",") > 10:
        return parse_csv(text)
    raise StatementError("Формат не распознан: поддерживаются выгрузка 1С «Клиент-Банк» и CSV")


def analyze(p: Parsed, declared_monthly_revenue: float | None = None,
            fns_annual_revenue: float | None = None) -> dict:
    months: dict[str, dict] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0, "excluded": 0.0, "count": 0})
    by_cp: dict[str, float] = defaultdict(float)
    excluded_total = 0.0
    for tx in p.txs:
        key = f"{tx.day:%Y-%m}"
        m = months[key]
        m["count"] += 1
        if tx.amount > 0:
            reason = tx.excluded or ("займ / собственные средства" if NOT_REVENUE.search(tx.purpose) else None)
            if reason:
                m["excluded"] += tx.amount
                excluded_total += tx.amount
                continue
            m["inflow"] += tx.amount
            by_cp[tx.counterparty or "без названия"] += tx.amount
        else:
            m["outflow"] += -tx.amount

    keys = sorted(months)
    # Неполные крайние месяцы искажают среднее — берём только полные, если их ≥ 3
    full = keys[1:-1] if len(keys) >= 5 else keys
    inflow_total = sum(months[k]["inflow"] for k in full)
    outflow_total = sum(months[k]["outflow"] for k in full)
    n = max(1, len(full))
    avg_in, avg_out = inflow_total / n, outflow_total / n
    all_inflow = sum(by_cp.values())
    top = sorted(by_cp.items(), key=lambda kv: -kv[1])[:5]
    b2b = sorted(((n, v) for n, v in by_cp.items() if not RETAIL.search(n)), key=lambda kv: -kv[1])
    top_share = b2b[0][1] / all_inflow if b2b and all_inflow else 0.0
    values = [months[k]["inflow"] for k in full]
    volatility = (max(values) - min(values)) / avg_in if values and avg_in else 0.0

    flags = []
    deviation = None
    if declared_monthly_revenue:
        deviation = (avg_in - declared_monthly_revenue) / declared_monthly_revenue
        if deviation < -0.25:
            flags.append(f"Поступления по выписке на {abs(deviation):.0%} ниже заявленной выручки")
    if fns_annual_revenue:
        fns_dev = (avg_in * 12 - fns_annual_revenue) / fns_annual_revenue
        if abs(fns_dev) > 0.4:
            flags.append(f"Обороты по выписке расходятся с отчётностью ФНС на {abs(fns_dev):.0%}")
    if top_share > 0.5:
        flags.append(f"Высокая зависимость от одного покупателя ({b2b[0][0]}): {top_share:.0%} поступлений")
    if volatility > 0.8:
        flags.append("Сильные колебания выручки по месяцам — возможна сезонность")
    if len(keys) < 3:
        flags.append("Выписка короче 3 месяцев — для надёжной оценки нужно 6")

    return {
        "format": p.fmt,
        "account": p.account,
        "period_from": min(t.day for t in p.txs).isoformat(),
        "period_to": max(t.day for t in p.txs).isoformat(),
        "transactions": len(p.txs),
        "months": [{"month": k, **{kk: round(v) if isinstance(v, float) else v for kk, v in months[k].items()},
                    "full": k in full} for k in keys],
        "months_used": len(full),
        "avg_monthly_inflow": round(avg_in),
        "avg_monthly_outflow": round(avg_out),
        "excluded_total": round(excluded_total),
        "top_counterparties": [{"name": name, "amount": round(v), "share": round(v / all_inflow, 3) if all_inflow else 0}
                               for name, v in top],
        "top_share": round(top_share, 3),
        "volatility": round(volatility, 2),
        "declared_monthly_revenue": declared_monthly_revenue,
        "deviation_from_declared": round(deviation, 3) if deviation is not None else None,
        "confirms_declared": deviation is not None and deviation >= -0.25,
        "flags": flags,
    }
