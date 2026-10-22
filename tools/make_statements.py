"""Генерация синтетических банковских выписок для демо-компаний.

Создаёт файлы в frontend/public/samples/ (их можно скачать прямо из интерфейса):
* выписки в формате 1С «Клиент-Банк» (windows-1251) — Колосок, СтройМонтаж, Флора;
* CSV-выписку Колосок — для демонстрации второго формата.

Запуск: python tools/make_statements.py
"""
import calendar
import csv
import io
import pathlib
import random
import zlib
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "samples"
START, END = date(2026, 3, 20), date(2026, 10, 15)  # 6 полных месяцев + неполные края

COMPANIES = {
    "kolosok": {
        "inn": "7701234561", "name": "ООО «Колосок»", "account": "40702810400000012345", "monthly": 4_350_000,
        "clients": [("ООО «Продукты у дома»", 0.18), ("ООО «Кофейня на углу»", 0.14), ("ИП Орлова Т.В.", 0.12),
                    ("ООО «Школьное питание»", 0.12), ("ООО «Сеть Вкусно»", 0.1), ("АО «Гастроном №1»", 0.1),
                    ("ООО «Ресторан Река»", 0.08), ("ИП Белов А.А.", 0.06), ("Розничная выручка (эквайринг)", 0.1)],
        "goods": "хлебобулочные изделия", "season": {}, "extra": "kolosok",
    },
    "stroy": {
        "inn": "7703456789", "name": "ООО «СтройМонтаж Плюс»", "account": "40702810900000067890", "monthly": 9_800_000,
        "clients": [("АО «ГК Девелопмент»", 0.62), ("ООО «ЖилСтрой»", 0.2), ("ГБУ «Дирекция ремонта»", 0.12),
                    ("ООО «ТехноПарк»", 0.06)],
        "goods": "электромонтажные работы", "season": {}, "extra": None,
    },
    "flora": {
        "inn": "772012345678", "name": "ИП Смирнова Анна Сергеевна", "account": "40802810100000054321", "monthly": 720_000,
        "clients": [("Розничная выручка (эквайринг)", 0.7), ("ООО «Ивент-Агентство»", 0.18), ("ООО «Отель Центр»", 0.12)],
        "goods": "цветы и букеты", "season": {9: 1.6, 5: 1.2}, "extra": None,
    },
}

SUPPLIERS = [("ООО «Мука и Ко»", 0.35), ("ООО «Аренда-Сервис»", 0.12), ("УФК по г. Москве (ИФНС)", 0.08),
             ("Зарплатный проект", 0.3), ("ООО «Энергосбыт»", 0.05), ("ООО «Логистика»", 0.1)]


def _h(s: str) -> int:
    return zlib.crc32(s.encode("utf-8"))


def fake_inn(name: str) -> str:
    return str(_h(name) * 7919 % 10**10).rjust(10, "7")


def gen(code: str) -> list[dict]:
    c = COMPANIES[code]
    rnd = random.Random(code)
    txs = []
    d = START
    while d <= END:
        dim = calendar.monthrange(d.year, d.month)[1]
        k = c["season"].get(d.month, 1.0)
        if d.weekday() < 6:
            for name, share in c["clients"]:
                if rnd.random() < 0.45:
                    amount = c["monthly"] * k * share / (dim * 0.45 * 6 / 7) * rnd.uniform(0.6, 1.4)
                    txs.append({"date": d, "amount": round(amount, 2), "cp": name, "cp_inn": fake_inn(name),
                                "purpose": f"Оплата по счёту № {rnd.randint(100, 999)} за {c['goods']}. НДС не облагается"})
            if rnd.random() < 0.5:
                name, share = rnd.choice(SUPPLIERS)
                amount = c["monthly"] * 0.85 * share / (dim * 0.5 * 6 / 7) * rnd.uniform(0.6, 1.4)
                txs.append({"date": d, "amount": -round(amount, 2), "cp": name, "cp_inn": fake_inn(name),
                            "purpose": f"Оплата по договору № {rnd.randint(10, 99)}"})
        d += timedelta(days=1)
    if c["extra"] == "kolosok":
        # Не выручка: перевод со своего счёта в другом банке и займ учредителя
        txs.append({"date": date(2026, 6, 10), "amount": 800_000.0, "cp": c["name"], "cp_inn": c["inn"],
                    "purpose": "Перевод собственных средств с расчётного счёта в другом банке"})
        txs.append({"date": date(2026, 8, 3), "amount": 500_000.0, "cp": "Иванов Пётр Сергеевич", "cp_inn": "770100000099",
                    "purpose": "Предоставление займа учредителем по договору займа № 3"})
    return sorted(txs, key=lambda t: t["date"])


def to_1c(code: str, txs: list[dict]) -> str:
    c = COMPANIES[code]
    fmt = lambda d: d.strftime("%d.%m.%Y")  # noqa: E731
    lines = ["1CClientBankExchange", "ВерсияФормата=1.03", "Кодировка=Windows", "Отправитель=Бухгалтерский учет",
             "Получатель=", f"ДатаСоздания={fmt(date(2026, 10, 16))}", "ВремяСоздания=10:15:00",
             f"ДатаНачала={fmt(START)}", f"ДатаКонца={fmt(END)}", f"РасчСчет={c['account']}",
             "Документ=Платежное поручение", "СекцияРасчСчет", f"ДатаНачала={fmt(START)}", f"ДатаКонца={fmt(END)}",
             f"РасчСчет={c['account']}", "НачальныйОстаток=1250000.00",
             f"ВсегоПоступило={sum(t['amount'] for t in txs if t['amount'] > 0):.2f}",
             f"ВсегоСписано={-sum(t['amount'] for t in txs if t['amount'] < 0):.2f}", "КонецРасчСчет"]
    for i, t in enumerate(txs, 1):
        incoming = t["amount"] > 0
        other_acc = "40702810" + str(_h(t["cp"]) * 104729 % 10**12).rjust(12, "0")
        payer = (t["cp"], t["cp_inn"], other_acc) if incoming else (c["name"], c["inn"], c["account"])
        payee = (c["name"], c["inn"], c["account"]) if incoming else (t["cp"], t["cp_inn"], other_acc)
        lines += ["СекцияДокумент=Платежное поручение", f"Номер={i}", f"Дата={fmt(t['date'])}",
                  f"Сумма={abs(t['amount']):.2f}", f"ПлательщикСчет={payer[2]}", f"Плательщик=ИНН {payer[1]} {payer[0]}",
                  f"ПлательщикИНН={payer[1]}", f"Плательщик1={payer[0]}", f"ПолучательСчет={payee[2]}",
                  f"Получатель=ИНН {payee[1]} {payee[0]}", f"ПолучательИНН={payee[1]}", f"Получатель1={payee[0]}",
                  f"{'ДатаПоступило' if incoming else 'ДатаСписано'}={fmt(t['date'])}",
                  f"НазначениеПлатежа={t['purpose']}", "КонецДокумента"]
    lines.append("КонецФайла")
    return "\r\n".join(lines) + "\r\n"


def to_csv(txs: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Дата операции", "Контрагент", "Назначение платежа", "Приход", "Расход"])
    for t in txs:
        amt = f"{abs(t['amount']):.2f}".replace(".", ",")
        w.writerow([t["date"].strftime("%d.%m.%Y"), t["cp"], t["purpose"],
                    amt if t["amount"] > 0 else "", amt if t["amount"] < 0 else ""])
    return buf.getvalue()


# Синтетические выписки с заранее заложенными ошибками — для демонстрации проверки документов
COMPANIES["vector"] = {**COMPANIES["kolosok"], "inn": "7705123456", "name": "ООО «Вектор»",
                       "account": "40702810700000099999", "monthly": 4_100_000, "extra": None,
                       "clients": [("ООО «Сеть Вкусно»", 0.4), ("ИП Белов А.А.", 0.3), ("АО «Гастроном №1»", 0.3)]}
COMPANIES["kolosok_low"] = {**COMPANIES["kolosok"], "monthly": 1_500_000, "extra": None}
ERROR_SAMPLES = {
    "vypiska_oshibka_chuzhaya_1c.txt": ("vector", None),        # выписка другой компании
    "vypiska_oshibka_nizkie_oboroty_1c.txt": ("kolosok_low", None),  # обороты ниже анкеты
    "vypiska_oshibka_2_mesyaca_1c.txt": ("kolosok", (date(2026, 8, 1), date(2026, 9, 30))),  # короткий период
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (code, period) in ERROR_SAMPLES.items():
        txs = [t for t in gen(code) if not period or period[0] <= t["date"] <= period[1]]
        (OUT / name).write_bytes(to_1c(code, txs).encode("cp1251"))
        print(f"{name}: {len(txs)} операций")
    for code in ("kolosok", "stroy", "flora"):
        txs = gen(code)
        (OUT / f"vypiska_{code}_1c.txt").write_bytes(to_1c(code, txs).encode("cp1251"))
        print(f"{code}: {len(txs)} операций")
    (OUT / "vypiska_kolosok.csv").write_text(to_csv(gen("kolosok")), encoding="utf-8-sig")
    print("written to", OUT)


if __name__ == "__main__":
    main()
