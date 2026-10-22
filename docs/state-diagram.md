# Диаграмма состояний заявки

Переходы описаны в [`backend/app/domain/state_machine.py`](../backend/app/domain/state_machine.py). Любой другой переход отклоняется (HTTP 409), каждый успешный — пишется в журнал аудита.

```mermaid
stateDiagram-v2
    [*] --> DRAFT: клиент создал черновик
    DRAFT --> SUBMITTED: клиент отправил
    DRAFT --> CANCELLED: клиент

    SUBMITTED --> DATA_CHECK: система (приём)
    DATA_CHECK --> ENRICHMENT: данные полные
    DATA_CHECK --> INFO_REQUESTED: не хватает документов

    ENRICHMENT --> SCORING: ЕГРЮЛ, ФНС, БКИ получены
    ENRICHMENT --> MANUAL_REVIEW: источник недоступен
    ENRICHMENT --> REJECTED: стоп-фактор ЕГРЮЛ

    SCORING --> APPROVED: в пределах лимита
    SCORING --> COUNTER_OFFER: другая сумма / срок / продукт
    SCORING --> INFO_REQUESTED: подтвердить данные
    SCORING --> MANUAL_REVIEW: вне полномочий автоматики
    SCORING --> REJECTED: стоп-факторы

    MANUAL_REVIEW --> APPROVED: андеррайтер
    MANUAL_REVIEW --> COUNTER_OFFER: андеррайтер
    MANUAL_REVIEW --> INFO_REQUESTED: андеррайтер
    MANUAL_REVIEW --> REJECTED: андеррайтер

    INFO_REQUESTED --> SUBMITTED: все запрошенные документы загружены (автоматически)

    APPROVED --> SIGNING: клиент принял условия
    COUNTER_OFFER --> SIGNING: клиент выбрал вариант
    SIGNING --> ISSUING: подпись ПЭП
    ISSUING --> DISBURSED: система перечислила средства

    INFO_REQUESTED --> CANCELLED: клиент
    MANUAL_REVIEW --> CANCELLED: клиент
    APPROVED --> CANCELLED: отказ клиента
    COUNTER_OFFER --> CANCELLED: отказ клиента
    SIGNING --> CANCELLED: клиент

    DISBURSED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
```

| Статус | Для клиента | Кто двигает дальше |
|---|---|---|
| `DRAFT` | Черновик | Клиент |
| `SUBMITTED` | Заявка отправлена | Воркер |
| `DATA_CHECK` | Проверка данных | Воркер |
| `ENRICHMENT` | Запрос сведений ЕГРЮЛ, ФНС, БКИ | Воркер |
| `SCORING` | Оценка и решение | Воркер |
| `MANUAL_REVIEW` | Рассматривает специалист | Андеррайтер |
| `INFO_REQUESTED` | Нужны дополнительные данные | Клиент |
| `APPROVED` | Одобрено | Клиент |
| `COUNTER_OFFER` | Предложены другие условия | Клиент |
| `SIGNING` | Подписание договора | Клиент |
| `ISSUING` | Выдача средств | Воркер |
| `DISBURSED` | Средства выданы | — (финал) |
| `REJECTED` | Отказ | — (финал) |
| `CANCELLED` | Отменена | — (финал) |

Клиенту показывается укрупнённый трек из 5 шагов: **Заявка → Проверка → Решение → Подписание → Деньги на счёте**, а внутри шага «Проверка» — детальные подэтапы в реальном времени.
