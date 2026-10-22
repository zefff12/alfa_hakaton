"""Запись демо: проходит основные сценарии в браузере, сохраняет видео и скриншоты.

Требуется запущенный стек (docker compose up) и Playwright:
    pip install playwright
    python tools/record_demo.py [--base http://localhost:8080] [--out demo]
Используется установленный Microsoft Edge (channel="msedge"), скачивать браузер не нужно.
Лучше запускать на чистой базе: docker compose down -v && docker compose up -d
"""
import argparse
import pathlib
import shutil

from playwright.sync_api import Page, sync_playwright

W, H = 1440, 900
SAMPLES = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "public" / "samples"


def shot(page: Page, out: pathlib.Path, name: str, full: bool = False) -> None:
    page.wait_for_timeout(400)
    page.screenshot(path=out / f"{name}.png", full_page=full)
    print("screenshot", name)


def pause(page: Page, ms: int = 1200) -> None:
    page.wait_for_timeout(ms)


def login(page: Page, base: str, company: str) -> None:
    page.goto(f"{base}/login")
    page.evaluate("localStorage.clear()")
    page.goto(f"{base}/login")
    page.get_by_text(company, exact=True).first.click()
    page.wait_for_url(lambda u: "/login" not in u)
    pause(page)


def say(page: Page, text: str, wait: int = 1600) -> None:
    box = page.get_by_placeholder("Например: нужно 2 млн на оборудование, верну за 3 года…")
    box.click()
    box.type(text, delay=28)
    box.press("Enter")
    pause(page, wait)


def prepare_manual_review(page: Page, base: str) -> None:
    """Через API готовим заявку «СтройМонтажа» с выпиской, которая доходит до андеррайтера."""
    req = page.context.request
    tok = req.post(f"{base}/api/auth/login", data={"login": "stroy", "password": "demo"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    app = req.post(f"{base}/api/applications", headers=h, data={
        "product_code": "WORKING", "purpose": "working_capital", "amount": 15_000_000, "term_months": 36}).json()
    app = req.patch(f"{base}/api/applications/{app['id']}", headers=h, data={
        "version": app["version"], "purpose_comment": "Закупка кабеля и щитового оборудования под объекты 2027 года",
        "form_data": {"monthly_revenue": 13_000_000, "monthly_expenses": 7_500_000, "existing_payments": 520_000},
        "consents": {"bki": True, "personal_data": True}}).json()
    files = [("bank_statement", "vypiska_stroy_1c.txt", "text/plain", (SAMPLES / "vypiska_stroy_1c.txt").read_bytes()),
             ("tax_certificate", "spravka_fns.pdf", "application/pdf", b"%PDF-1.4 demo")]
    for code, name, mime, data in files:
        req.post(f"{base}/api/applications/{app['id']}/documents", headers=h, multipart={
            "doc_type": code, "file": {"name": name, "mimeType": mime, "buffer": data}})
    req.post(f"{base}/api/applications/{app['id']}/submit", headers=h, data={})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--out", default="demo")
    args = ap.parse_args()
    base, out = args.base, pathlib.Path(args.out)
    shots = out / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", slow_mo=100)
        ctx = browser.new_context(viewport={"width": W, "height": H}, locale="ru-RU",
                                  record_video_dir=str(out / "raw"), record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        prepare_manual_review(page, base)  # обрабатывается в фоне, пока идёт демо клиента

        # 1. Вход и главная
        page.goto(f"{base}/login")
        pause(page, 1500)
        shot(page, shots, "01-login")
        login(page, base, "ООО «Колосок»")
        shot(page, shots, "02-home")

        # 2. Фишка №1 — «Расскажите Альфику»
        page.get_by_role("link", name="Рассказать Альфику").first.click()
        pause(page, 1200)
        shot(page, shots, "03-talk-start")
        say(page, "Нужно 2 млн на новую печь, верну за 3 года, выручка около 4,5 млн в месяц", 2200)
        shot(page, shots, "04-talk-understood")
        say(page, "примерно 3,6 млн")
        say(page, "плачу 180 тысяч в месяц по кредиту на оборудование")
        say(page, "да, сама печь", 2200)
        shot(page, shots, "05-talk-ready")
        page.get_by_role("button", name="Создать черновик заявки").click()
        page.wait_for_url("**/applications/*")
        pause(page, 1500)
        shot(page, shots, "06-draft-prefilled")

        # 3. Фишка №2 — Альфик читает выписку
        page.get_by_role("button", name="4. Документы").click()
        pause(page)
        page.locator(".upload", has_text="Коммерческое предложение").locator("input[type=file]").set_input_files(
            {"name": "kp_pech.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 offer"})
        pause(page, 800)
        page.locator(".upload", has_text="Выписка по расчётному счёту").locator("input[type=file]").set_input_files(
            str(SAMPLES / "vypiska_kolosok_1c.txt"))
        page.wait_for_selector("text=Альфик прочитал выписку")
        page.locator(".st-chart").scroll_into_view_if_needed()
        pause(page, 2500)
        shot(page, shots, "07-statement")
        page.get_by_role("button", name="3. Финансы").click()
        pause(page, 1500)
        shot(page, shots, "08-finance")
        page.get_by_role("button", name="5. Отправка").click()
        page.get_by_text("Согласен на обработку персональных данных").click()
        page.get_by_text("Согласен на запрос кредитной истории").click()
        pause(page)
        page.get_by_role("button", name="Отправить заявку в банк").click()

        # 4. Живой конвейер → решение → подпись → выдача
        page.wait_for_selector("text=Что происходит с заявкой")
        page.wait_for_timeout(5000)
        shot(page, shots, "09-pipeline-live")
        page.wait_for_selector("text=Ваше предложение", timeout=60_000)
        pause(page, 1500)
        shot(page, shots, "10-approved")
        page.get_by_role("button", name="Принять и перейти к подписанию").click()
        page.wait_for_selector(".code")
        pause(page, 1200)
        code = page.locator(".code").inner_text().strip()
        page.get_by_placeholder("••••••").type(code, delay=110)
        shot(page, shots, "11-signing")
        page.get_by_role("button", name="Подписать договор").click()
        page.wait_for_selector("text=Кредит выдан", timeout=60_000)
        pause(page, 1200)
        page.locator("summary", has_text="График платежей").click()
        pause(page)
        shot(page, shots, "12-disbursed")

        # 5. Чат с Альфиком и персональная лента
        page.get_by_role("button", name="Открыть чат с Альфиком").click()
        pause(page)
        page.get_by_placeholder("Напишите вопрос…").type("Что такое овердрафт и когда он лучше кредита?", delay=25)
        page.keyboard.press("Enter")
        pause(page, 2200)
        page.locator(".chat-quick button", has_text="Какой статус заявки?").click()
        pause(page, 2200)
        shot(page, shots, "13-alfik-chat")
        page.get_by_role("button", name="Закрыть").click()
        page.get_by_role("link", name="Лента Альфика").click()
        pause(page, 1800)
        shot(page, shots, "14-feed-bakery")

        # 6. Другой клиент: подбор с «платёж слишком высокий» и «Каковы мои шансы?»
        login(page, base, "ИП Смирнова Анна Сергеевна")
        page.get_by_role("link", name="Подобрать кредит").first.click()
        page.get_by_role("button", name="Пополнить оборотные средства (закупка товара, сырья)").click()
        page.get_by_role("button", name="3 000 000 ₽").click()
        page.get_by_role("button", name="12 мес.").click()
        page.get_by_role("button", name="Нет залога").click()
        page.get_by_role("button", name="Могу подождать пару дней").click()
        pause(page, 1500)
        page.get_by_role("button", name="Платёж слишком высокий для меня").click()
        comfort = page.get_by_placeholder("Комфортный платёж")
        comfort.fill("")
        comfort.type("120000", delay=50)
        page.get_by_role("button", name="Подобрать условия").click()
        pause(page, 1800)
        shot(page, shots, "15-calculator-comfort")
        page.get_by_role("link", name="Мои шансы").click()
        page.get_by_label("Сумма кредита").fill("")
        page.get_by_label("Сумма кредита").type("3000000", delay=25)
        page.get_by_label("Сколько месяцев работает бизнес?").fill("26")
        page.get_by_label("Средняя выручка в месяц").type("800000", delay=25)
        page.get_by_label("Средние расходы в месяц").type("600000", delay=25)
        page.get_by_label("Платежи по текущим кредитам в месяц").type("15000", delay=25)
        page.get_by_role("button", name="Оценить шансы").click()
        page.wait_for_selector("text=готовность")
        pause(page, 2000)
        shot(page, shots, "16-precheck")
        page.get_by_role("link", name="Лента Альфика").click()
        pause(page, 1600)
        shot(page, shots, "17-feed-flowers")

        # 7. Фишка №3 — консоль андеррайтера с резюме Альфика
        login(page, base, "Сотрудник банка")
        pause(page, 1500)
        shot(page, shots, "18-bank-queue")
        page.locator("tr.click").first.click()
        page.wait_for_selector("text=Резюме Альфика")
        pause(page, 2500)
        shot(page, shots, "19-bank-summary")
        page.locator(".st-chart").scroll_into_view_if_needed()
        pause(page, 2500)
        shot(page, shots, "20-bank-statement")
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        pause(page)
        page.get_by_role("button", name="Изменить условия").click()
        amount = page.locator(".card", has_text="Решение специалиста").get_by_role("textbox").first
        amount.fill("")
        amount.type("11000000", delay=35)
        page.locator("textarea").fill("Лимит снижен по фактическим оборотам из выписки; запрошен договор с ГК Девелопмент")
        page.get_by_role("button", name="Зафиксировать решение").click()
        pause(page, 2200)
        shot(page, shots, "21-bank-decision")

        ctx.close()
        browser.close()

    raw = next((out / "raw").glob("*.webm"))
    shutil.move(str(raw), out / "alfik-demo.webm")
    shutil.rmtree(out / "raw", ignore_errors=True)
    print("video", out / "alfik-demo.webm")


if __name__ == "__main__":
    main()
