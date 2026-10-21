"""Генерация Postman-коллекции: сквозной сценарий + все эндпоинты из OpenAPI.

Запуск: python tools/make_postman.py  (из корня репозитория)
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))


def req(name, method, path, body=None, tests=None, auth="{{token}}"):
    item = {
        "name": name,
        "request": {
            "method": method,
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": {"raw": "{{baseUrl}}" + path, "host": ["{{baseUrl}}"], "path": [p for p in path.split("/") if p]},
        },
    }
    if auth:
        item["request"]["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": auth, "type": "string"}]}
    if body is not None:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, ensure_ascii=False, indent=2)}
    if tests:
        item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": tests}}]
    return item


login_test = lambda var: [
    "pm.test('200', () => pm.response.to.have.status(200));",
    f"pm.collectionVariables.set('{var}', pm.response.json().access_token);",
]

scenario = [
    req("1. Вход клиента (Колосок)", "POST", "/api/auth/login", {"login": "kolosok", "password": "demo"},
        login_test("token"), auth=None),
    req("2. Подбор продукта Альфиком", "POST", "/api/advisor/recommend",
        {"purpose": "working_capital", "amount": 3000000, "term_months": 24, "has_collateral": False}),
    req("3. Каковы мои шансы?", "POST", "/api/precheck",
        {"product_code": "WORKING", "amount": 3000000, "term_months": 24, "business_age_months": 90,
         "monthly_revenue": 4500000, "monthly_expenses": 3600000, "existing_monthly_payments": 180000}),
    req("4. Создать черновик", "POST", "/api/applications",
        {"product_code": "WORKING", "purpose": "working_capital", "amount": 3000000, "term_months": 24},
        ["pm.test('201', () => pm.response.to.have.status(201));",
         "pm.collectionVariables.set('appId', pm.response.json().id);"]),
    req("5. Заполнить анкету и согласия", "PATCH", "/api/applications/{{appId}}",
        {"form_data": {"monthly_revenue": 4500000, "monthly_expenses": 3600000, "existing_payments": 180000},
         "consents": {"bki": True, "personal_data": True}}),
    req("6. Отправить заявку", "POST", "/api/applications/{{appId}}/submit", {},
        ["pm.test('SUBMITTED', () => pm.expect(pm.response.json().status).to.eql('SUBMITTED'));"]),
    req("7. Статус (повторять ~10 сек до APPROVED)", "GET", "/api/applications/{{appId}}", None,
        ["const a = pm.response.json(); console.log(a.status);",
         "if (a.offer) pm.collectionVariables.set('optionId', a.offer.options[0].id);",
         "if (a.signing) pm.collectionVariables.set('signCode', a.signing.demo_code);"]),
    req("8. Принять предложение", "POST", "/api/applications/{{appId}}/accept", {"option_id": "{{optionId}}"},
        ["pm.collectionVariables.set('signCode', pm.response.json().signing.demo_code);"]),
    req("9. Подписать договор (ПЭП)", "POST", "/api/applications/{{appId}}/sign", {"code": "{{signCode}}"}),
    req("10. Итог: DISBURSED и график", "GET", "/api/applications/{{appId}}", None,
        ["pm.test('DISBURSED', () => pm.expect(pm.response.json().status).to.eql('DISBURSED'));"]),
    req("11. Вопрос Альфику", "POST", "/api/assistant/chat", {"message": "Какой статус моей заявки?"}),
    req("12. Персональная лента", "GET", "/api/feed"),
    req("13. Вход андеррайтера", "POST", "/api/auth/login", {"login": "underwriter", "password": "demo"},
        login_test("uwToken"), auth=None),
    req("14. Очередь ручного рассмотрения", "GET", "/api/bank/applications?queue=manual", auth="{{uwToken}}"),
    req("15. Метрики конвейера", "GET", "/api/bank/metrics", auth="{{uwToken}}"),
]

all_items = []
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        p = path.replace("{app_id}", "{{appId}}").replace("{doc_id}", "1").replace("{inn}", "7701234561")
        auth = "{{uwToken}}" if path.startswith("/api/bank") else "{{token}}"
        all_items.append(req(f"{method.upper()} {path} — {op.get('summary', '')}", method.upper(), p, auth=auth))

collection = {
    "info": {
        "name": "Умный кредитный кабинет — API",
        "description": "Сквозной сценарий и полный перечень эндпоинтов. baseUrl по умолчанию — http://localhost:8000",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [{"key": "baseUrl", "value": "http://localhost:8000"}, {"key": "token", "value": ""},
                 {"key": "uwToken", "value": ""}, {"key": "appId", "value": ""}, {"key": "optionId", "value": "opt1"},
                 {"key": "signCode", "value": ""}],
    "item": [{"name": "Сквозной сценарий (E2E)", "item": scenario}, {"name": "Все эндпоинты", "item": all_items}],
}
out = ROOT / "docs" / "postman_collection.json"
out.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"written {out} ({len(scenario)} scenario + {len(all_items)} endpoints)")
