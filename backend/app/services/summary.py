"""Резюме заявки для кредитного специалиста: всё важное — в одном блоке.

Собирается детерминированно из результатов конвейера (источники, скоринг,
решение, выписка, документы), поэтому каждое утверждение проверяемо.
"""
from app.domain.products import DOCUMENT_TYPES, get_product
from app.domain.scoring import INDUSTRY_NAMES
from app.models import Application
from app.services.pipeline import business_age_months, latest_statement


def _m(v) -> str:
    return f"{float(v):,.0f} ₽".replace(",", " ")


def _pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def build(app: Application) -> dict | None:
    if not app.scoring and not app.enrichment:
        return None
    product = get_product(app.product_code)
    src = (app.enrichment or {}).get("sources", {})
    egrul, fns, bki = src.get("egrul") or {}, src.get("fns") or {}, src.get("bki") or {}
    sc, dec, fd = app.scoring or {}, app.decision or {}, app.form_data or {}
    stmt = latest_statement(app)
    points: list[dict] = []

    def add(kind: str, text: str) -> None:
        points.append({"kind": kind, "text": text})

    age = business_age_months(egrul.get("registered_at") or app.company.registered_at)
    industry = INDUSTRY_NAMES.get(egrul.get("industry") or app.company.industry or "other", "другое")
    add("info", f"{app.company.name}: {industry}, на рынке {age // 12} г. {age % 12} мес.; запрошено "
                f"{_m(app.amount)} на {app.term_months} мес. ({product.name if product else '—'}).")

    if sc:
        factors = sc.get("factors", [])
        neg = [f for f in sorted(factors, key=lambda f: f["points"]) if f["points"] < 0][:2]
        pos = [f for f in sorted(factors, key=lambda f: -f["points"]) if f["points"] > 0][:2]
        add("info", f"Скоринг {sc['score']} — класс {sc['risk_class']} ({sc['risk_label'].lower()}), PD ≈ {_pct(sc['pd'])}"
                    + (f", долговая нагрузка {_pct(sc['debt_burden'])}" if sc.get("debt_burden") is not None else "") + ".")
        if pos:
            add("ok", "Сильные стороны: " + "; ".join(f"{f['name'].lower()} ({f['value']})" for f in pos) + ".")
        if neg:
            add("warn", "Слабые места: " + "; ".join(f"{f['name'].lower()} ({f['value']})" for f in neg) + ".")

    # Сверка данных из разных источников
    declared = float(fd.get("monthly_revenue") or 0)
    if declared and fns.get("annual_revenue"):
        dev = (declared * 12 - fns["annual_revenue"]) / fns["annual_revenue"]
        add("ok" if abs(dev) <= 0.4 else "risk",
            f"Выручка со слов клиента {_m(declared * 12)}/год против {_m(fns['annual_revenue'])} по ФНС ({'+' if dev >= 0 else ''}{_pct(dev)}).")
    if stmt:
        sdev = (stmt["avg_monthly_inflow"] - declared) / declared if declared else None
        text = f"Выписка ({stmt['months_used']} мес.): очищенные поступления {_m(stmt['avg_monthly_inflow'])}/мес"
        if sdev is not None:
            text += f", к анкете {'+' if sdev >= 0 else ''}{_pct(sdev)}"
        if stmt.get("excluded_total"):
            text += f"; исключено {_m(stmt['excluded_total'])} (свои переводы, займы)"
        add("ok" if sdev is None or sdev >= -0.25 else "risk", text + ".")
        for flag in stmt.get("flags", []):
            if "ниже заявленной" not in flag:
                add("warn", flag + ".")
    if bki:
        declared_pay = float(fd.get("existing_payments") or 0)
        bki_pay = float(bki.get("total_monthly_payments") or 0)
        if bki_pay > declared_pay * 1.2 + 1000:
            add("risk", f"По БКИ платежи {_m(bki_pay)}/мес, клиент указал {_m(declared_pay)} — нагрузка недооценена.")
        if bki.get("max_delinquency_days_12m"):
            add("warn", f"Просрочка до {bki['max_delinquency_days_12m']} дн. за 12 мес. ({bki.get('delinquencies_12m', 0)} случ.).")
    if fns.get("tax_arrears"):
        add("warn", f"Налоговая задолженность по ФНС: {_m(fns['tax_arrears'])}.")
    if egrul.get("mass_address"):
        add("risk", "Адрес массовой регистрации — проверить фактическое место ведения бизнеса.")

    for e in (app.enrichment or {}).get("errors", []):
        add("risk", f"Источник недоступен: {e['service']} — данные нужно получить вручную.")

    if app.status == "MANUAL_REVIEW":
        reasons = [r["text"] for r in dec.get("reasons", []) if r.get("text")]
        if reasons:
            add("info", "Почему у специалиста: " + "; ".join(reasons) + ".")

    docs = [DOCUMENT_TYPES.get(d.doc_type, d.doc_type) for d in app.documents if d.status != "REJECTED"]
    if docs:
        add("info", "Документы: " + ", ".join(docs) + ".")

    rec = dec.get("recommendation") or {}
    recommendation = None
    if rec and rec.get("advice") == "decline":
        recommendation = (f"Платёжеспособности не хватает даже на минимальную сумму продукта (лимит {_m(rec['limit'])}) — "
                          f"движок склоняется к отказу или другому продукту.")
    elif rec:
        recommendation = (f"Движок рекомендует {_m(rec['amount'])} под {rec['rate']:g}% на {rec['term_months']} мес. "
                          f"(лимит по платёжеспособности {_m(rec['limit'])}).")
    checks = []
    if any(p["kind"] == "risk" for p in points):
        checks.append("подтвердить расхождения документами или звонком клиенту")
    if stmt and stmt.get("top_share", 0) > 0.5:
        checks.append("запросить договор с крупнейшим покупателем и график его оплат")
    if fns.get("tax_arrears"):
        checks.append("убедиться, что справка ФНС актуальна на дату решения")
    if bki.get("max_delinquency_days_12m"):
        checks.append("уточнить причину просрочки")

    risks = sum(p["kind"] == "risk" for p in points)
    warns = sum(p["kind"] == "warn" for p in points)
    verdict = "high" if risks >= 2 else "medium" if risks or warns >= 2 else "low"
    return {
        "verdict": verdict,
        "verdict_label": {"low": "Существенных рисков не выявлено", "medium": "Есть моменты для проверки",
                          "high": "Требует внимательной проверки"}[verdict],
        "points": points,
        "recommendation": recommendation,
        "checks": checks,
    }
