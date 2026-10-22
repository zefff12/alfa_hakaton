"""«Кредитный подбор» — предложения карточками, которые клиент листает свайпами.

Принципы ранжирования:
1. Сначала — реальное соответствие требованиям (цель, сумма, срок, возраст
   бизнеса, залог): неподходящие варианты не показываются как «лучшие».
2. Затем — что важнее самому предпринимателю: низкая переплата, скорость
   или минимальный пакет документов (он выбирает это до подбора).
3. Свайпы уточняют предпочтения: признаки понравившихся вариантов получают
   больший вес, пропущенных — меньший, и колода перестраивается.
Доходность продукта для банка в ранжировании не участвует.
"""
from dataclasses import dataclass, field

from app.domain import calculator
from app.domain.advisor import NeedProfile, recommend
from app.domain.products import DOCUMENT_TYPES, PRODUCT_META, PRODUCTS, PURPOSES, Product, required_documents_for

PRIORITIES = {
    "cost": "Низкая переплата",
    "speed": "Скорость получения",
    "docs": "Минимум документов",
    "balanced": "Всё одинаково важно",
}
FEATURES = ("cost", "speed", "docs", "no_collateral")
BASE_WEIGHTS = {
    "cost": {"cost": 2.5, "speed": 0.3, "docs": 0.3, "no_collateral": 0.2},
    "speed": {"cost": 0.3, "speed": 2.5, "docs": 0.4, "no_collateral": 0.3},
    "docs": {"cost": 0.3, "speed": 0.4, "docs": 2.5, "no_collateral": 0.4},
    "balanced": {"cost": 0.6, "speed": 0.6, "docs": 0.6, "no_collateral": 0.3},
}
INSIGHT = {
    "cost": "Похоже, для вас важнее низкая переплата — поднял варианты с меньшей стоимостью кредита.",
    "speed": "Похоже, для вас важнее скорость — поднял варианты с быстрым решением.",
    "docs": "Похоже, вам важен минимальный пакет документов — поднял варианты без лишних бумаг.",
    "no_collateral": "Похоже, вы предпочитаете кредит без залога — поднял беззалоговые варианты.",
}


@dataclass
class MatchProfile:
    purpose: str = "working_capital"
    amount: int = 3_000_000
    term_months: int = 24
    has_collateral: bool = False
    deferral: bool = False
    priority: str = "balanced"
    business_age_months: int = 24
    monthly_revenue: float | None = None
    likes: list[str] = field(default_factory=list)
    skips: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None, business_age_months: int = 24) -> "MatchProfile":
        data = data or {}
        known = {k: data[k] for k in ("purpose", "amount", "term_months", "has_collateral", "deferral", "priority",
                                      "monthly_revenue", "likes", "skips") if k in data and data[k] is not None}
        prof = cls(business_age_months=business_age_months, **known)
        if prof.priority not in PRIORITIES:
            prof.priority = "balanced"
        return prof

    def to_dict(self) -> dict:
        return {"purpose": self.purpose, "amount": self.amount, "term_months": self.term_months,
                "has_collateral": self.has_collateral, "deferral": self.deferral, "priority": self.priority,
                "monthly_revenue": self.monthly_revenue, "likes": self.likes, "skips": self.skips,
                "business_age_months": self.business_age_months}


def offer_for(product: Product, prof: MatchProfile, amount: int | None = None, term: int | None = None) -> dict:
    """Персональное предложение: условия, расчёт, почему подходит и что потребуется."""
    amount = int(amount or prof.amount)
    term = int(term or prof.term_months)
    amount_c = min(max(amount, product.min_amount), product.max_amount)
    term_c = min(max(term, product.min_term), product.max_term)
    rate = round(product.base_rate + (1.5 if not (prof.has_collateral and product.collateral == "optional") else -0.5), 1)
    calc = calculator.summary(amount_c, rate, term_c, product.revolving)
    meta = PRODUCT_META[product.code]
    docs = required_documents_for(product, amount_c, prof.purpose)

    fits: list[str] = []
    gaps: list[str] = []
    if prof.purpose in product.purposes:
        fits.append(f"Соответствует цели «{PURPOSES.get(prof.purpose, prof.purpose)}»")
    elif "other" in product.purposes:
        fits.append("Можно потратить на любые цели бизнеса")
    else:
        gaps.append("Предназначен для других целей")
    if amount_c == amount and term_c == term:
        fits.append("Подходит под желаемую сумму и срок")
    else:
        gaps.append(f"Условия скорректированы: {calculator.round_amount(amount_c):,} ₽ на {term_c} мес.".replace(",", " "))
    if product.collateral == "none":
        fits.append("Можно оформить без залога")
    elif product.collateral == "required":
        (fits if prof.has_collateral else gaps).append("Нужен залог — подойдёт приобретаемое имущество")
    elif prof.has_collateral:
        fits.append("С залогом ставка ниже")
    if prof.deferral:
        if product.code == "WORKING":
            fits.append("Есть отсрочка платежа по основному долгу")
        else:
            gaps.append("Отсрочки по основному долгу нет")
    if prof.business_age_months < product.min_business_age_months:
        gaps.append(f"Нужен бизнес старше {product.min_business_age_months} мес.")
    if not docs:
        fits.append("Документы не нужны — данные банк получит сам")
    if meta["speed_hours"] <= 1:
        fits.append(f"Быстрое решение: {product.decision_time}")
    if prof.monthly_revenue and not product.revolving and calc["monthly_payment"] > prof.monthly_revenue * 0.3:
        gaps.append("Платёж больше 30% месячной выручки")

    return {
        "code": product.code,
        "name": product.name,
        "short": product.short,
        "description": product.description,
        "amount": amount_c,
        "term_months": term_c,
        "rate": rate,
        "monthly_payment": calc["monthly_payment"],
        "total_interest": calc["total_interest"],
        "total_repayment": calc["total_repayment"],
        "revolving": product.revolving,
        "max_amount": product.max_amount,
        "min_amount": product.min_amount,
        "min_term": product.min_term,
        "max_term": product.max_term,
        "collateral": product.collateral,
        "decision_time": product.decision_time,
        "speed_hours": meta["speed_hours"],
        "form": meta["form"],
        "early_repayment": meta["early_repayment"],
        "feature": meta["feature"],
        "documents": [{"code": d, "label": DOCUMENT_TYPES[d]} for d in docs],
        "fits": fits,
        "gaps": gaps,
        "eligible": not any("старше" in g or "других целей" in g for g in gaps)
                    and (product.collateral != "required" or prof.has_collateral),
    }


def _features(offers: list[dict]) -> dict[str, dict[str, float]]:
    """Нормированные признаки 0..1: чем больше, тем лучше для клиента."""
    def norm(values: dict[str, float], invert: bool) -> dict[str, float]:
        lo, hi = min(values.values()), max(values.values())
        return {k: 1.0 if hi == lo else ((hi - v) if invert else (v - lo)) / (hi - lo) for k, v in values.items()}
    # Переплата в расчёте на год: у продуктов разные сроки, сравнивать полную переплату нечестно
    cost = norm({o["code"]: o["total_interest"] / max(o["amount"], 1) / (o["term_months"] / 12) for o in offers},
                invert=True)
    speed = norm({o["code"]: o["speed_hours"] for o in offers}, invert=True)
    docs = norm({o["code"]: len(o["documents"]) for o in offers}, invert=True)
    return {o["code"]: {"cost": cost[o["code"]], "speed": speed[o["code"]], "docs": docs[o["code"]],
                        "no_collateral": 1.0 if o["collateral"] == "none" else 0.0} for o in offers}


def learned_weights(prof: MatchProfile, feats: dict[str, dict[str, float]]) -> tuple[dict[str, float], str | None]:
    weights = dict(BASE_WEIGHTS[prof.priority])
    liked = [feats[c] for c in prof.likes if c in feats]
    skipped = [feats[c] for c in prof.skips if c in feats]
    if not liked and not skipped:
        return weights, None
    delta = {}
    for f in FEATURES:
        like_avg = sum(x[f] for x in liked) / len(liked) if liked else 0.5
        skip_avg = sum(x[f] for x in skipped) / len(skipped) if skipped else 0.5
        delta[f] = like_avg - skip_avg
        weights[f] = max(0.05, weights[f] + 0.8 * delta[f])
    top = max(delta, key=lambda f: delta[f])
    insight = INSIGHT[top] if delta[top] > 0.25 and len(prof.likes) + len(prof.skips) >= 2 else None
    return weights, insight


def build_deck(prof: MatchProfile) -> dict:
    fit = {i["product"]["code"]: i["fit_score"] for i in recommend(NeedProfile(
        purpose=prof.purpose, amount=prof.amount, term_months=prof.term_months,
        business_age_months=prof.business_age_months, has_collateral=prof.has_collateral,
        monthly_revenue=prof.monthly_revenue))["items"]}
    offers = [offer_for(p, prof) for p in PRODUCTS.values()]
    feats = _features(offers)
    weights, insight = learned_weights(prof, feats)
    total_w = sum(weights.values())
    for o in offers:
        pref = sum(weights[f] * feats[o["code"]][f] for f in FEATURES) / total_w
        # Соответствие требованиям весит больше предпочтений: неподходящее не обгонит подходящее
        o["fit_score"] = fit[o["code"]]
        o["score"] = round(0.65 * fit[o["code"]] + 35 * pref - (40 if not o["eligible"] else 0), 1)
        o["match_percent"] = max(0, min(99, round(o["score"])))
    offers.sort(key=lambda o: -o["score"])
    if offers and offers[0]["eligible"]:
        offers[0]["recommended"] = True
    seen = set(prof.likes) | set(prof.skips)
    deck = [o for o in offers if o["code"] not in seen]
    return {
        "profile": prof.to_dict(),
        "priority_label": PRIORITIES[prof.priority],
        "offers": offers,
        "deck": deck,
        "insight": insight,
        "weights": {k: round(v, 2) for k, v in weights.items()},
        "stats": {"total": len(offers), "liked": len(prof.likes), "skipped": len(prof.skips), "left": len(deck)},
    }


COMPARE_ROWS = [
    ("purpose", "Цель"), ("amount", "Сумма кредита"), ("term", "Срок"), ("rate", "Процентная ставка"),
    ("payment", "Ежемесячный платёж"), ("total", "Общая сумма выплат"), ("collateral", "Обеспечение"),
    ("speed", "Скорость получения"), ("form", "Форма выдачи"), ("early", "Досрочное погашение"), ("feature", "Особенности"),
]
COLLATERAL_LABEL = {"none": "Без залога", "optional": "Залог по желанию", "required": "С залогом"}


def compare(offers: list[dict], prof: MatchProfile) -> dict:
    def money(v: float) -> str:
        return f"{v:,.0f} ₽".replace(",", " ")

    cols = []
    for o in offers:
        p = PRODUCTS[o["code"]]
        cols.append({
            "code": o["code"], "name": o["name"], "short": o["short"], "recommended": o.get("recommended", False),
            "cells": {
                "purpose": PURPOSES.get(p.purposes[0], ""),
                "amount": f"до {money(p.max_amount)}",
                "term": f"до {p.max_term} мес.",
                "rate": f"от {o['rate']}% годовых",
                "payment": f"от {money(o['monthly_payment'])}",
                "total": money(o["total_repayment"]),
                "collateral": COLLATERAL_LABEL[p.collateral],
                "speed": p.decision_time,
                "form": o["form"], "early": o["early_repayment"], "feature": o["feature"],
            },
            # Лучшие значения по строкам подсвечиваются в интерфейсе
            "raw": {"rate": o["rate"], "payment": o["monthly_payment"], "total": o["total_repayment"],
                    "speed": o["speed_hours"]},
        })
    best = {}
    for key in ("rate", "payment", "total", "speed"):
        if cols:
            best[key] = min(cols, key=lambda c: c["raw"][key])["code"]
    return {"rows": [{"key": k, "label": label} for k, label in COMPARE_ROWS], "columns": cols, "best": best,
            "params": {"amount": prof.amount, "term_months": prof.term_months}}
