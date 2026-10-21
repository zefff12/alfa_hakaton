"""Кредитный калькулятор: аннуитет, обратный расчёт, график платежей."""
import math
from datetime import date


def monthly_payment(amount: float, annual_rate: float, term_months: int) -> float:
    if amount <= 0 or term_months <= 0:
        return 0.0
    r = annual_rate / 100 / 12
    if r == 0:
        return amount / term_months
    return amount * r / (1 - (1 + r) ** -term_months)


def max_amount_for_payment(payment: float, annual_rate: float, term_months: int) -> float:
    """Какую сумму можно взять при заданном комфортном платеже."""
    if payment <= 0 or term_months <= 0:
        return 0.0
    r = annual_rate / 100 / 12
    if r == 0:
        return payment * term_months
    return payment * (1 - (1 + r) ** -term_months) / r


def min_term_for_payment(amount: float, annual_rate: float, payment: float, max_term: int) -> int | None:
    """Минимальный срок, при котором платёж не превышает заданный."""
    for term in range(1, max_term + 1):
        if monthly_payment(amount, annual_rate, term) <= payment:
            return term
    return None


def summary(amount: float, annual_rate: float, term_months: int, revolving: bool = False) -> dict:
    if revolving:
        # Для овердрафта показываем стоимость полного использования лимита в течение месяца
        interest_month = amount * annual_rate / 100 / 12
        return {
            "amount": round(amount),
            "rate": annual_rate,
            "term_months": term_months,
            "monthly_payment": round(interest_month),
            "total_interest": round(interest_month * term_months),
            "total_repayment": round(amount + interest_month * term_months),
            "revolving": True,
        }
    pay = monthly_payment(amount, annual_rate, term_months)
    total = pay * term_months
    return {
        "amount": round(amount),
        "rate": annual_rate,
        "term_months": term_months,
        "monthly_payment": round(pay),
        "total_interest": round(total - amount),
        "total_repayment": round(total),
        "revolving": False,
    }


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


def schedule(amount: float, annual_rate: float, term_months: int, start: date | None = None) -> list[dict]:
    start = start or date.today()
    r = annual_rate / 100 / 12
    pay = monthly_payment(amount, annual_rate, term_months)
    balance = amount
    rows = []
    for i in range(1, term_months + 1):
        interest = balance * r
        principal = pay - interest if i < term_months else balance
        balance = max(0.0, balance - principal)
        rows.append(
            {
                "n": i,
                "date": _add_months(start, i).isoformat(),
                "payment": round(principal + interest, 2),
                "principal": round(principal, 2),
                "interest": round(interest, 2),
                "balance": round(balance, 2),
            }
        )
    return rows


def round_amount(value: float, step: int = 10_000) -> int:
    return int(math.floor(value / step) * step)
