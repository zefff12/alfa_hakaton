"""Синтетические демо-данные: компании и тестовые учётные записи (пароль у всех — demo)."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, User
from app.security import hash_password

log = logging.getLogger("seed")

COMPANIES = [
    dict(inn="7701234561", name="ООО «Колосок»", legal_form="ООО", okved="10.71",
         okved_name="Производство хлеба и мучных кондитерских изделий", industry="food", region="Москва",
         director="Иванов Пётр Сергеевич", registered_at="2019-03-12", ogrn="1197746123456",
         address="г. Москва, ул. Пекарская, д. 7"),
    dict(inn="772012345678", name="ИП Смирнова Анна Сергеевна", legal_form="ИП", okved="47.76",
         okved_name="Торговля розничная цветами и растениями", industry="retail", region="Москва",
         director="Смирнова Анна Сергеевна", registered_at="2024-08-01", ogrn="324774600123456",
         address="г. Москва, ул. Цветочная, д. 3"),
    dict(inn="7703456789", name="ООО «СтройМонтаж Плюс»", legal_form="ООО", okved="43.21",
         okved_name="Производство электромонтажных работ", industry="construction", region="Московская область",
         director="Кузнецов Алексей Викторович", registered_at="2016-05-20", ogrn="1167746987654",
         address="МО, г. Химки, ул. Строителей, д. 12"),
    dict(inn="7704567890", name="ООО «Ромашка Трейд»", legal_form="ООО", okved="46.90",
         okved_name="Торговля оптовая неспециализированная", industry="retail", region="Москва",
         director="Петров Иван Иванович", registered_at="2020-02-10", ogrn="1207700555444",
         address="г. Москва, ул. Лесная, д. 1, оф. 999"),
    dict(inn="7700000000", name="ООО «Тест Отказоустойчивость»", legal_form="ООО", okved="62.01",
         okved_name="Разработка компьютерного программного обеспечения", industry="it", region="Москва",
         director="Сбоев Сергей Сергеевич", registered_at="2018-01-15", ogrn="1187700000000",
         address="г. Москва, ул. Облачная, д. 5"),
]

USERS = [
    dict(login="kolosok", full_name="Пётр Иванов", position="Генеральный директор", inn="7701234561",
         hint="Пекарня 7 лет на рынке, чистая кредитная история → автоматическое одобрение"),
    dict(login="flora", full_name="Анна Смирнова", position="Индивидуальный предприниматель", inn="772012345678",
         hint="Молодой цветочный бизнес: большая сумма → банк предложит другие условия"),
    dict(login="stroy", full_name="Мария Кузнецова", position="Финансовый директор", inn="7703456789",
         hint="Налоговый долг → запрос справки; сумма > 10 млн → решение андеррайтера"),
    dict(login="romashka", full_name="Иван Петров", position="Директор", inn="7704567890",
         hint="Компания в процессе ликвидации → отказ с понятным объяснением"),
    dict(login="failover", full_name="Сергей Сбоев", position="Директор", inn="7700000000",
         hint="БКИ недоступно → конвейер не падает, заявка уходит специалисту"),
    dict(login="underwriter", full_name="Елена Соколова", position="Кредитный аналитик МСБ", inn=None, role="underwriter",
         hint="Консоль банка: очередь, скоринг, ручное решение"),
]


def seed(db: Session) -> None:
    if db.scalar(select(User).limit(1)):
        return
    by_inn = {}
    for c in COMPANIES:
        company = Company(**c)
        db.add(company)
        by_inn[c["inn"]] = company
    db.flush()
    for u in USERS:
        db.add(User(
            login=u["login"], password_hash=hash_password("demo"), role=u.get("role", "client"),
            full_name=u["full_name"], position=u["position"], demo_hint=u["hint"],
            company_id=by_inn[u["inn"]].id if u["inn"] else None,
        ))
    db.commit()
    log.info("demo data seeded: %s users", len(USERS))
