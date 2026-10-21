"""Симуляторы внешних источников данных для кредитного конвейера.

* ЕГРЮЛ/ЕГРИП — регистрационные данные и статус бизнеса;
* ФНС «Прозрачный бизнес» — выручка, налоговая задолженность, численность;
* БКИ — кредитная история и платёжная дисциплина (только при согласии клиента).

Контракты упрощены, но сохраняют смысл интеграций. Данные синтетические:
для известных демо-ИНН — фиксированные сценарии, для любого другого ИНН —
детерминированная генерация (один и тот же ИНН всегда даёт одни и те же данные).
"""
import hashlib
import os
import random
import time
import uuid
from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="External services mocks (ЕГРЮЛ, ФНС, БКИ)",
    version="1.0.0",
    description="Синтетические стабы внешних сервисов. Не являются реальными интеграциями.",
)

FAILURE_RATE = float(os.getenv("MOCK_FAILURE_RATE", "0"))
LATENCY_MS = int(os.getenv("MOCK_LATENCY_MS", "150"))
# ИНН, на котором БКИ всегда «недоступно» — демонстрация отказоустойчивости конвейера
BKI_DOWN_INN = "7700000000"

DEMO: dict[str, dict] = {
    "7701234561": {
        "egrul": {
            "name": "ООО «Колосок»", "full_name": "Общество с ограниченной ответственностью «Колосок»",
            "legal_form": "ООО", "ogrn": "1197746123456", "status": "ACTIVE", "registered_at": "2019-03-12",
            "okved": "10.71", "okved_name": "Производство хлеба и мучных кондитерских изделий",
            "industry": "food", "region": "Москва", "address": "г. Москва, ул. Пекарская, д. 7",
            "director": "Иванов Пётр Сергеевич", "mass_address": False, "director_disqualified": False,
        },
        "fns": {"annual_revenue": 54_000_000, "tax_arrears": 0, "employees": 38, "tax_regime": "УСН"},
        "bki": {"credit_history_months": 52, "max_delinquency_days_12m": 0, "delinquencies_12m": 0,
                "loans": [{"bank": "Банк А", "type": "Кредит на оборудование", "balance": 2_400_000,
                           "monthly_payment": 180_000, "overdue_days": 0}]},
    },
    "772012345678": {
        "egrul": {
            "name": "ИП Смирнова Анна Сергеевна", "full_name": "Индивидуальный предприниматель Смирнова Анна Сергеевна",
            "legal_form": "ИП", "ogrn": "324774600123456", "status": "ACTIVE", "registered_at": "2024-08-01",
            "okved": "47.76", "okved_name": "Торговля розничная цветами и растениями",
            "industry": "retail", "region": "Москва", "address": "г. Москва, ул. Цветочная, д. 3",
            "director": "Смирнова Анна Сергеевна", "mass_address": False, "director_disqualified": False,
        },
        "fns": {"annual_revenue": 9_600_000, "tax_arrears": 0, "employees": 4, "tax_regime": "Патент"},
        "bki": {"credit_history_months": 14, "max_delinquency_days_12m": 0, "delinquencies_12m": 0,
                "loans": [{"bank": "Банк Б", "type": "Кредитная карта", "balance": 150_000,
                           "monthly_payment": 15_000, "overdue_days": 0}]},
    },
    "7703456789": {
        "egrul": {
            "name": "ООО «СтройМонтаж Плюс»", "full_name": "Общество с ограниченной ответственностью «СтройМонтаж Плюс»",
            "legal_form": "ООО", "ogrn": "1167746987654", "status": "ACTIVE", "registered_at": "2016-05-20",
            "okved": "43.21", "okved_name": "Производство электромонтажных работ",
            "industry": "construction", "region": "Московская область", "address": "МО, г. Химки, ул. Строителей, д. 12",
            "director": "Кузнецов Алексей Викторович", "mass_address": False, "director_disqualified": False,
        },
        "fns": {"annual_revenue": 120_000_000, "tax_arrears": 64_000, "employees": 85, "tax_regime": "ОСН"},
        "bki": {"credit_history_months": 70, "max_delinquency_days_12m": 12, "delinquencies_12m": 1,
                "loans": [{"bank": "Банк В", "type": "Оборотный кредит", "balance": 8_000_000,
                           "monthly_payment": 520_000, "overdue_days": 0}]},
    },
    "7704567890": {
        "egrul": {
            "name": "ООО «Ромашка Трейд»", "full_name": "Общество с ограниченной ответственностью «Ромашка Трейд»",
            "legal_form": "ООО", "ogrn": "1207700555444", "status": "LIQUIDATING", "registered_at": "2020-02-10",
            "okved": "46.90", "okved_name": "Торговля оптовая неспециализированная",
            "industry": "retail", "region": "Москва", "address": "г. Москва, ул. Лесная, д. 1, оф. 999",
            "director": "Петров Иван Иванович", "mass_address": True, "director_disqualified": False,
        },
        "fns": {"annual_revenue": 3_200_000, "tax_arrears": 410_000, "employees": 1, "tax_regime": "ОСН"},
        "bki": {"credit_history_months": 30, "max_delinquency_days_12m": 45, "delinquencies_12m": 3,
                "loans": [{"bank": "Банк Г", "type": "Кредит", "balance": 900_000,
                           "monthly_payment": 95_000, "overdue_days": 45}]},
    },
}

INDUSTRIES = [
    ("47.11", "Торговля розничная в неспециализированных магазинах", "retail"),
    ("56.10", "Деятельность ресторанов и услуги по доставке продуктов питания", "food"),
    ("62.01", "Разработка компьютерного программного обеспечения", "it"),
    ("49.41", "Деятельность автомобильного грузового транспорта", "transport"),
    ("96.02", "Предоставление услуг парикмахерскими и салонами красоты", "services"),
    ("25.62", "Обработка металлических изделий механическая", "manufacturing"),
    ("41.20", "Строительство жилых и нежилых зданий", "construction"),
    ("86.23", "Стоматологическая практика", "medicine"),
]


def _rng(inn: str) -> random.Random:
    return random.Random(int(hashlib.sha256(inn.encode()).hexdigest(), 16))


def _generated(inn: str) -> dict:
    r = _rng(inn)
    okved, okved_name, industry = r.choice(INDUSTRIES)
    is_ip = len(inn) == 12
    years = r.randint(1, 10)
    reg = date(date.today().year - years, r.randint(1, 12), r.randint(1, 28))
    revenue = r.choice([4, 8, 15, 25, 40, 70]) * 1_000_000
    bad = r.random() < 0.15
    name_part = f"{r.choice(['Альтаир', 'Вектор', 'Гранит', 'Меридиан', 'Сфера', 'Импульс', 'Орбита'])}"
    return {
        "egrul": {
            "name": f"ИП Предприниматель {inn[-4:]}" if is_ip else f"ООО «{name_part}-{inn[-3:]}»",
            "full_name": f"{'Индивидуальный предприниматель' if is_ip else 'Общество с ограниченной ответственностью'} {name_part}",
            "legal_form": "ИП" if is_ip else "ООО",
            "ogrn": f"3{inn}00" if is_ip else f"1{inn}00",
            "status": "ACTIVE", "registered_at": reg.isoformat(), "okved": okved, "okved_name": okved_name,
            "industry": industry, "region": "Москва", "address": f"г. Москва, ул. Тестовая, д. {r.randint(1, 99)}",
            "director": "Тестов Тест Тестович", "mass_address": False, "director_disqualified": False,
        },
        "fns": {"annual_revenue": revenue, "tax_arrears": r.choice([0, 0, 0, 30_000]) , "employees": r.randint(2, 60),
                "tax_regime": r.choice(["УСН", "ОСН", "Патент"])},
        "bki": {
            "credit_history_months": r.choice([0, 12, 24, 48]),
            "max_delinquency_days_12m": r.choice([10, 40]) if bad else 0,
            "delinquencies_12m": 1 if bad else 0,
            "loans": [] if r.random() < 0.4 else [{
                "bank": "Банк Д", "type": "Кредит", "balance": revenue * 0.1,
                "monthly_payment": round(revenue * 0.004), "overdue_days": 0}],
        },
    }


def _record(inn: str) -> dict:
    if not inn.isdigit() or len(inn) not in (10, 12):
        raise HTTPException(status_code=422, detail="ИНН должен содержать 10 (ЮЛ) или 12 (ИП) цифр")
    return DEMO.get(inn) or _generated(inn)


def _simulate_network():
    if LATENCY_MS:
        time.sleep(LATENCY_MS / 1000)
    if FAILURE_RATE and random.random() < FAILURE_RATE:
        raise HTTPException(status_code=503, detail="Сервис временно недоступен (симуляция сбоя)")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/egrul/{inn}", tags=["ЕГРЮЛ/ЕГРИП"], summary="Выписка из ЕГРЮЛ/ЕГРИП")
def egrul(inn: str):
    _simulate_network()
    return {"inn": inn, "source": "EGRUL_MOCK", **_record(inn)["egrul"]}


@app.get("/fns/{inn}", tags=["ФНС"], summary="Сведения сервиса «Прозрачный бизнес»")
def fns(inn: str):
    _simulate_network()
    data = _record(inn)["fns"]
    return {"inn": inn, "source": "FNS_TRANSPARENT_BUSINESS_MOCK", "revenue_year": date.today().year - 1, **data}


class BkiRequest(BaseModel):
    inn: str
    consent_id: str = Field(min_length=6, description="Идентификатор согласия клиента на запрос кредитной истории")
    purpose: str = "loan_application"


@app.post("/bki/report", tags=["БКИ"], summary="Кредитный отчёт")
def bki(req: BkiRequest):
    if req.inn == BKI_DOWN_INN:
        raise HTTPException(status_code=503, detail="БКИ недоступно")
    _simulate_network()
    data = _record(req.inn)["bki"]
    total = sum(l["monthly_payment"] for l in data["loans"])
    bki_score = max(300, 850 - data["max_delinquency_days_12m"] * 3 - (0 if data["credit_history_months"] else 80))
    return {
        "inn": req.inn,
        "report_id": str(uuid.uuid4()),
        "source": "BKI_MOCK",
        "consent_id": req.consent_id,
        "credit_history_months": data["credit_history_months"],
        "max_delinquency_days_12m": data["max_delinquency_days_12m"],
        "delinquencies_12m": data["delinquencies_12m"],
        "active_loans": data["loans"],
        "total_monthly_payments": total,
        "bki_score": bki_score,
    }
