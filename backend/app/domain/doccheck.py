"""Проверка документов и анкеты на несоответствия — до передачи заявки на рассмотрение.

Каждая проверка показывает значения и их источники (анкета, выписка, ФНС, БКИ,
ЕГРЮЛ) и, если ошибку можно исправить, предлагает исправление одним действием.
Так ассистент экономит время сотрудника и находит ошибки до рассмотрения.
"""
from app.domain.products import DOCUMENT_TYPES, get_product, required_documents_for


def _m(v) -> str:
    return f"{float(v):,.0f} ₽".replace(",", " ")


def _period(stmt: dict) -> str:
    months = [m["month"] for m in stmt.get("months", []) if m.get("full")] or [m["month"] for m in stmt.get("months", [])]
    if not months:
        return ""
    def fmt(ym: str) -> str:
        y, mm = ym.split("-")
        return f"{mm}.{y}"
    return f"{fmt(months[0])}–{fmt(months[-1])}"


def run(app, stmt: dict | None, provided_docs: set[str]) -> list[dict]:
    fd = app.form_data or {}
    src = (app.enrichment or {}).get("sources", {})
    fns, bki = src.get("fns") or {}, src.get("bki") or {}
    product = get_product(app.product_code)
    checks: list[dict] = []

    def add(code, title, status, message, values=None, fix=None, hint=None):
        checks.append({"code": code, "title": title, "status": status, "message": message,
                       "values": values or [], "fix": fix, "hint": hint})

    # 1. Анкета
    missing = [label for key, label in (("monthly_revenue", "выручка"), ("monthly_expenses", "расходы"))
               if fd.get(key) in (None, "")]
    if not app.product_code or not app.amount or not app.term_months:
        missing.insert(0, "параметры кредита")
    add("form", "Анкета на кредит", "error" if missing else "ok",
        ("Не заполнено: " + ", ".join(missing)) if missing else "Все обязательные поля заполнены")

    # 2. Выписка: чья, за какой период, сходятся ли обороты
    declared = float(fd.get("monthly_revenue") or 0)
    if stmt:
        period = _period(stmt)
        owner = stmt.get("owner_inn")
        if owner and owner != app.company.inn:
            add("statement_owner", "Владелец выписки", "error",
                "Выписка принадлежит другой компании — загрузите выписку по своему расчётному счёту",
                [{"label": "ИНН в выписке", "value": owner, "origin": "Выписка 1С"},
                 {"label": "ИНН компании", "value": app.company.inn, "origin": "ЕГРЮЛ"}])
        else:
            add("statement_owner", "Владелец выписки", "ok", "Выписка по счёту вашей компании",
                [{"label": "ИНН", "value": app.company.inn, "origin": "Выписка 1С и ЕГРЮЛ"}] if owner else [])
        used = stmt.get("months_used", 0)
        add("statement_period", "Период выписки", "ok" if used >= 6 else "warn",
            f"Полных месяцев в выписке: {used}" + ("" if used >= 6 else " — для надёжной оценки нужно 6"),
            [{"label": "Период", "value": period, "origin": "Выписка"}])
        if declared and not (owner and owner != app.company.inn):
            avg = stmt["avg_monthly_inflow"]
            dev = (avg - declared) / declared
            status = "ok" if dev >= -0.15 else "warn" if dev >= -0.25 else "error"
            add("revenue_statement", "Выручка: анкета и выписка", status,
                "Выручка подтверждена выпиской" if status == "ok"
                else f"Поступления по выписке на {abs(dev):.0%} ниже выручки в анкете",
                [{"label": "Выручка в месяц", "value": _m(declared), "origin": "Анкета"},
                 {"label": "Очищенные поступления в месяц", "value": _m(avg), "origin": f"Выписка ({period})"}],
                fix=None if status == "ok" else {"field": "monthly_revenue", "value": round(avg),
                                                 "label": f"Указать {_m(avg)} из выписки"})
    else:
        add("statement", "Выписка по счёту", "info", "Выписка не загружена — проверим выручку по данным ФНС",
            hint="Загрузите выписку 1С или CSV — я сверю обороты с анкетой")

    # 3. Сведения внешних источников (появляются после отправки заявки)
    if fns.get("annual_revenue") and declared:
        dev = (declared * 12 - fns["annual_revenue"]) / fns["annual_revenue"]
        status = "ok" if abs(dev) <= 0.25 else "warn" if abs(dev) <= 0.4 else "error"
        add("revenue_fns", "Выручка: анкета и ФНС", status,
            "Совпадает с отчётностью" if status == "ok" else f"Расхождение с отчётностью ФНС {abs(dev):.0%}",
            [{"label": "Выручка в год", "value": _m(declared * 12), "origin": "Анкета"},
             {"label": "Выручка в год", "value": _m(fns["annual_revenue"]), "origin": f"ФНС, {fns.get('revenue_year', '')}"}],
            fix=None if status == "ok" else {"field": "monthly_revenue", "value": round(fns["annual_revenue"] / 12),
                                             "label": f"Указать {_m(fns['annual_revenue'] / 12)} по данным ФНС"})
    elif declared:
        add("revenue_fns", "Выручка: анкета и ФНС", "pending", "Сверим с отчётностью ФНС после отправки заявки")

    if bki:
        declared_pay = float(fd.get("existing_payments") or 0)
        bki_pay = float(bki.get("total_monthly_payments") or 0)
        ok = bki_pay <= declared_pay * 1.2 + 1000
        add("payments_bki", "Платежи по кредитам: анкета и БКИ", "ok" if ok else "warn",
            "Совпадает с кредитной историей" if ok else "В кредитной истории есть платежи, которых нет в анкете",
            [{"label": "Платежи в месяц", "value": _m(declared_pay), "origin": "Анкета"},
             {"label": "Платежи в месяц", "value": _m(bki_pay), "origin": "БКИ"}],
            fix=None if ok else {"field": "existing_payments", "value": round(bki_pay),
                                 "label": f"Указать {_m(bki_pay)} по данным БКИ"})
    if fns.get("tax_arrears"):
        has_cert = "tax_certificate" in provided_docs
        add("tax", "Налоговая задолженность", "ok" if has_cert else "warn",
            "Справка об отсутствии долга приложена" if has_cert else "По данным ФНС есть долг — приложите справку",
            [{"label": "Долг", "value": _m(fns["tax_arrears"]), "origin": "ФНС"}])

    # 4. Обязательные документы продукта
    if product:
        need = required_documents_for(product, app.amount, app.purpose)
        lacking = [d for d in need if d not in provided_docs]
        add("required_docs", "Обязательные документы", "warn" if lacking else "ok",
            ("Не хватает: " + "; ".join(DOCUMENT_TYPES[d] for d in lacking)) if lacking
            else "Все документы для продукта на месте" if need else "Для этого продукта документы не нужны")
    return checks


def summary(checks: list[dict]) -> dict:
    count = {s: sum(1 for c in checks if c["status"] == s) for s in ("ok", "warn", "error", "pending", "info")}
    level = "error" if count["error"] else "warn" if count["warn"] else "ok"
    return {"level": level, "counts": count, "fixable": sum(1 for c in checks if c.get("fix"))}
