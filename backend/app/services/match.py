"""Сценарии «Кредитного подбора»: профиль, свайпы, избранное, сравнение, оформление."""
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain import match
from app.domain.products import DECISION_VALID_DAYS, PRODUCTS, PURPOSES, get_product
from app.domain.state_machine import Actor
from app.models import Application, Favorite, MatchProfileRow, User
from app.services import pipeline
from app.services.applications import next_number

COLLATERAL_TEXT = {"none": "Без залога", "optional": "Залог по желанию — снижает ставку",
                   "required": "Залог — приобретаемое имущество"}


def _row(db: Session, user: User) -> MatchProfileRow:
    row = db.scalar(select(MatchProfileRow).where(MatchProfileRow.user_id == user.id))
    if not row:
        row = MatchProfileRow(user_id=user.id, data={})
        db.add(row)
        db.flush()
    return row


def load_profile(db: Session, user: User) -> match.MatchProfile:
    reg = user.company.registered_at if user.company else None
    age = pipeline.business_age_months(reg) if reg else 24
    data = dict(_row(db, user).data or {})
    if "monthly_revenue" not in data:
        last = db.scalar(select(Application).where(Application.company_id == user.company_id)
                         .order_by(Application.updated_at.desc()))
        if last and (last.form_data or {}).get("monthly_revenue"):
            data["monthly_revenue"] = float(last.form_data["monthly_revenue"])
    return match.MatchProfile.from_dict(data, business_age_months=age)


def save_profile(db: Session, user: User, patch: dict) -> match.MatchProfile:
    row = _row(db, user)
    data = {**(row.data or {}), **{k: v for k, v in patch.items() if v is not None}}
    if patch.get("reset_swipes"):
        data["likes"], data["skips"] = [], []
    data.pop("reset_swipes", None)
    row.data = data
    db.commit()
    return load_profile(db, user)


def deck(db: Session, user: User) -> dict:
    result = match.build_deck(load_profile(db, user))
    # Пока клиент не выбрал, что для него важно, кабинет сначала спрашивает об этом
    result["configured"] = "priority" in (_row(db, user).data or {})
    result["favorites"] = [f.product_code for f in favorites_rows(db, user)]
    return result


def swipe(db: Session, user: User, code: str, action: str) -> dict:
    if code not in PRODUCTS:
        raise HTTPException(404, "Продукт не найден")
    row = _row(db, user)
    data = dict(row.data or {})
    likes = [c for c in data.get("likes", []) if c != code]
    skips = [c for c in data.get("skips", []) if c != code]
    (likes if action == "like" else skips).append(code)
    data.update(likes=likes, skips=skips)
    row.data = data
    if action == "like":
        add_favorite(db, user, code, commit=False)
    db.commit()
    return deck(db, user)


def favorites_rows(db: Session, user: User) -> list[Favorite]:
    return list(db.scalars(select(Favorite).where(Favorite.user_id == user.id).order_by(Favorite.created_at)))


def add_favorite(db: Session, user: User, code: str, commit: bool = True) -> None:
    if code not in PRODUCTS:
        raise HTTPException(404, "Продукт не найден")
    if not db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.product_code == code)):
        db.add(Favorite(user_id=user.id, product_code=code, in_compare=True))
    if commit:
        db.commit()


def remove_favorite(db: Session, user: User, code: str | None) -> None:
    stmt = delete(Favorite).where(Favorite.user_id == user.id)
    if code:
        stmt = stmt.where(Favorite.product_code == code)
    db.execute(stmt)
    db.commit()


def toggle_compare(db: Session, user: User, code: str) -> None:
    fav = db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.product_code == code))
    if not fav:
        raise HTTPException(404, "Предложения нет в избранном")
    fav.in_compare = not fav.in_compare
    db.commit()


def favorites(db: Session, user: User) -> dict:
    prof = load_profile(db, user)
    built = {o["code"]: o for o in match.build_deck(prof)["offers"]}
    rows = favorites_rows(db, user)
    items = [{**built[f.product_code], "in_compare": f.in_compare} for f in rows if f.product_code in built]
    return {"items": items, "compare_count": sum(1 for i in items if i["in_compare"])}


def compare(db: Session, user: User, codes: list[str] | None) -> dict:
    prof = load_profile(db, user)
    built = {o["code"]: o for o in match.build_deck(prof)["offers"]}
    if not codes:
        codes = [f.product_code for f in favorites_rows(db, user) if f.in_compare]
    offers = [built[c] for c in codes if c in built]
    if len(offers) < 2:
        raise HTTPException(422, "Для сравнения выберите хотя бы два предложения")
    return match.compare(offers, prof)


def detail(db: Session, user: User, code: str, amount: int | None, term: int | None) -> dict:
    product = get_product(code)
    if not product:
        raise HTTPException(404, "Продукт не найден")
    prof = load_profile(db, user)
    built = {o["code"]: o for o in match.build_deck(prof)["offers"]}
    offer = match.offer_for(product, prof, amount, term)
    offer["recommended"] = built.get(code, {}).get("recommended", False)
    tags = (["Рекомендуем"] if offer["recommended"] else []) + \
        (["Без залога"] if product.collateral == "none" else []) + \
        (["Быстрое решение"] if offer["speed_hours"] <= 1 else []) + ["Онлайн-оформление"]
    is_fav = any(f.product_code == code for f in favorites_rows(db, user))
    return {
        "offer": offer,
        "tags": tags,
        "in_favorites": is_fav,
        "conditions": [
            {"icon": "target", "title": "Цель", "text": "; ".join(PURPOSES[p] for p in product.purposes if p in PURPOSES)},
            {"icon": "layers", "title": "Форма финансирования", "text": offer["form"]},
            {"icon": "shield", "title": "Обеспечение", "text": COLLATERAL_TEXT[product.collateral]},
            {"icon": "clock", "title": "Срок рассмотрения", "text": product.decision_time},
            {"icon": "calendar", "title": "Срок действия решения", "text": f"До {DECISION_VALID_DAYS} дней"},
        ],
        "documents": ["ИНН компании — сведения из ЕГРЮЛ банк получит сам"]
                     + [d["label"] for d in offer["documents"]]
                     + ["Выписка по счёту — по желанию, ускорит решение"],
        "advantages": list(product.highlights) + [offer["feature"]],
    }


def apply(db: Session, user: User, code: str, amount: int | None, term: int | None) -> Application:
    product = get_product(code)
    if not product:
        raise HTTPException(404, "Продукт не найден")
    prof = load_profile(db, user)
    offer = match.offer_for(product, prof, amount, term)
    purpose = prof.purpose if prof.purpose in product.purposes else product.purposes[0]
    form = {"monthly_revenue": prof.monthly_revenue} if prof.monthly_revenue else {}
    app = Application(
        number=next_number(db), company_id=user.company_id, user_id=user.id, status="DRAFT",
        product_code=code, purpose=purpose, amount=offer["amount"], term_months=offer["term_months"],
        has_collateral=prof.has_collateral and product.collateral != "none",
        form_data={**form, "source": "credit_match"}, consents={}, requested_documents=[],
    )
    db.add(app)
    db.flush()
    pipeline.log_event(db, app, "CREATED", "Черновик создан из «Кредитного подбора»", actor=Actor.CLIENT,
                       actor_id=user.id, to_status="DRAFT", payload={"product": code, "priority": prof.priority})
    db.commit()
    return app
