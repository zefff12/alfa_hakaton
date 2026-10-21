from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.integrations import clients
from app.models import User
from app.schemas import DemoAccount, LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.security import create_token, current_user, hash_password, verify_password
from app.services.applications import ensure_company

router = APIRouter(prefix="/api/auth", tags=["Авторизация"])


@router.post("/login", response_model=TokenResponse, summary="Вход по логину и паролю")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.login == req.login.strip().lower()))
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Неверный логин или пароль")
    return TokenResponse(access_token=create_token(user), user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenResponse, status_code=201,
             summary="Регистрация нового клиента по ИНН (реквизиты подтягиваются из ЕГРЮЛ)")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    login_ = req.login.strip().lower()
    if db.scalar(select(User).where(User.login == login_)):
        raise HTTPException(409, "Такой логин уже занят")
    name = None
    try:
        egrul = clients.fetch_egrul(req.inn)
        name = egrul.get("name")
    except clients.IntegrationError:
        egrul = None
    company = ensure_company(db, req.inn, name)
    if egrul:
        for key in ("ogrn", "okved", "okved_name", "industry", "region", "address", "director", "registered_at", "legal_form"):
            setattr(company, key, egrul.get(key) or getattr(company, key))
    user = User(login=login_, password_hash=hash_password(req.password), role="client",
                full_name=req.full_name, position=req.position, company_id=company.id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
def me(user: User = Depends(current_user)):
    return user


@router.get("/demo-accounts", response_model=list[DemoAccount], summary="Тестовые учётные записи для проверки")
def demo_accounts(db: Session = Depends(get_db)):
    users = db.scalars(select(User).where(User.demo_hint.is_not(None)).order_by(User.id)).all()
    return [DemoAccount(login=u.login, password="demo", role=u.role, full_name=u.full_name,
                        company=u.company.name if u.company else None, hint=u.demo_hint) for u in users]
