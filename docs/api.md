# API

* Интерактивная документация: **http://localhost:8000/docs** (Swagger UI), **/redoc**.
* Спецификация: [`openapi.json`](openapi.json) (OpenAPI 3.1, выгружается из кода).
* Коллекция запросов: [`postman_collection.json`](postman_collection.json) — папка «Сквозной сценарий (E2E)» проходит путь от входа до выдачи, папка «Все эндпоинты» содержит каждый метод. Переменная `baseUrl` = `http://localhost:8000`.

## Авторизация

`POST /api/auth/login` → `access_token` (JWT, HS256, 12 ч). Передаётся заголовком `Authorization: Bearer <token>`. Роли: `client` (видит только заявки своей компании) и `underwriter` (консоль банка, `/api/bank/*`).

## Основные группы

| Группа | Эндпоинты |
|---|---|
| Авторизация | `POST /api/auth/login`, `POST /api/auth/register`, `GET /api/auth/me`, `GET /api/auth/demo-accounts` |
| Справочники | `GET /api/catalog`, `POST /api/calculator`, `GET /api/company/lookup/{inn}` |
| Альфик | `POST /api/advisor/recommend`, `POST /api/precheck`, `POST /api/assistant/chat`, `GET /api/assistant/history`, `GET /api/assistant/status` |
| Заявки клиента | `GET/POST /api/applications`, `GET/PATCH /api/applications/{id}`, `GET …/validate`, `POST …/submit`, `…/resubmit`, `…/accept`, `…/sign`, `…/cancel`, `…/documents` |
| Лента и уведомления | `GET /api/feed`, `POST /api/feed/react`, `GET /api/notifications`, `POST /api/notifications/read-all` |
| Консоль банка | `GET /api/bank/applications?queue=manual\|processing\|waiting_client\|done`, `GET /api/bank/metrics`, `GET /api/bank/applications/{id}`, `POST …/assign`, `POST …/decision`, `POST /api/bank/documents/{id}/review`, `GET /api/bank/audit` |
| Служебные | `GET /health/live`, `GET /health/ready` |

## Пример: сквозной путь через curl

```bash
TOKEN=$(curl -s localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"login":"kolosok","password":"demo"}' | jq -r .access_token)

ID=$(curl -s localhost:8000/api/applications -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"product_code":"WORKING","purpose":"working_capital","amount":3000000,"term_months":24}' | jq .id)

curl -s -X PATCH localhost:8000/api/applications/$ID -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"form_data":{"monthly_revenue":4500000,"monthly_expenses":3600000,"existing_payments":180000},"consents":{"bki":true,"personal_data":true}}'

curl -s -X POST localhost:8000/api/applications/$ID/submit -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
sleep 12
curl -s localhost:8000/api/applications/$ID -H "Authorization: Bearer $TOKEN" | jq '{status, offer: .offer.options}'
```

## Ошибки

| Код | Когда |
|---|---|
| 401 | Нет или истёк токен |
| 403 | Роль не имеет доступа (клиент → `/api/bank`) |
| 404 | Заявка не найдена или принадлежит другой компании |
| 409 | Недопустимый переход статуса или устаревшая `version` (оптимистическая блокировка) |
| 413 / 415 | Файл больше 10 МБ / неподдерживаемый тип |
| 422 | Ошибка валидации; тело `{"detail": {"message": "...", "errors": ["..."]}}` |
| 503 | Внешний источник недоступен (автозаполнение по ИНН) |

Каждый ответ содержит `X-Request-ID` для поиска в логах.

## Контракты внешних сервисов (моки, порт 8090)

| Сервис | Запрос | Ключевые поля ответа |
|---|---|---|
| ЕГРЮЛ/ЕГРИП | `GET /egrul/{inn}` | `status`, `registered_at`, `okved`, `industry`, `director`, `mass_address`, `director_disqualified` |
| ФНС «Прозрачный бизнес» | `GET /fns/{inn}` | `annual_revenue`, `tax_arrears`, `employees`, `tax_regime` |
| БКИ | `POST /bki/report {inn, consent_id}` | `credit_history_months`, `max_delinquency_days_12m`, `active_loans[]`, `total_monthly_payments` |

Swagger моков: http://localhost:8090/docs
