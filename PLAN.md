# SWIPIES Traffic Attribution & Analytics — Implementation Plan (Phase 2: Plan)

**Version:** 1.0.0  
**Status:** PROPOSED FOR HUMAN REVIEW (GATE 2 REVIEW)  
**Track:** Track 3 (Traffic Attribution & Analytics)  
**Methodology:** SpecKit Workflow (Risk-First, TDD, Process Isolation, Hard Safety Gates)

---

## 1. Технологический стек и обоснование

* **Язык & Среда:** Python 3.10+ (строгая валидация схем через `pydantic` v2, типобезопасные dataclasses).
* **Фреймворк сервиса трекинга:** `Flask` 3.x (легковесный микро-сервис `src/tracker_service.py`, работающий в отдельном процессе Gunicorn на порту `127.0.0.1:5001`).
* **Веб-сервер & Reverse Proxy:** `Nginx` (изолированный upstream на порт 5001, rate-limiting `30 r/s`, таймаут `1s`, проброс `X-Forwarded-For`).
* **Хранилище данных атрибуции:**
  * **События сайта:** Локальная база SQLite в режиме WAL (`data/attribution.db`) для высокой скорости параллельной записи событий (`attribution_raw_events` и витрина `daily_attribution_summary`).
  * **Связка с платежами:** Прямое read-only подключение к локальной боевой MySQL (`127.0.0.1:3306`) под изолированным юзером `analytics_ro` (доступ только к `v_attribution_payments` с директивой `SET SESSION max_execution_time = 3000`).
* **Клиентский трекер:** Vanilla JavaScript (`web/public/swipies-tracker.js`, <3.5 КБ gzip, zero dependencies, Visibility API, Beacon API, 30-дневная cookie `_swp_utm`).
* **Математика и финансы:** Встроенный модуль `decimal.Decimal` (банковское округление `ROUND_HALF_UP` для расчета ROAS, CPL и выручки без потери центов).
* **CLI-интерфейс:** `typer` + `tabulate` (форматирование сводных таблиц в терминале) + `csv`.
* **Тестирование:** `pytest` (изолированные фикстуры, in-memory SQLite, `freezegun` для симуляции 30-дневного retention purge, AST-сканер для проверки Allow-List).

---

## 2. Архитектура модулей и структура каталогов

```
D:\ads agent\
├── AUDIT.md                             # Результаты аудита рекламных платформ (Фаза 0)
├── SPEC.md                              # Утверждённая спецификация Track 3 (Фаза 1)
├── PLAN.md                              # Настоящий архитектурный план (Фаза 2)
├── TASKS.md                             # Детальный чек-лист задач реализации (Фаза 3)
├── .env.example                         # Шаблон локальной конфигурации
├── .gitignore                           # Изоляция секретов, баз данных и логов
├── requirements.txt                     # Зависимости трека атрибуции
├── migrations/
│   ├── V1.5__add_attribution_utm_columns.sql   # Аддитивная миграция payment_transaction
│   ├── V1.6__create_v_attribution_payments.sql # DDL создания безопасного View
│   └── V1.7__create_attribution_events.sql     # DDL таблиц сырых событий и витрин
├── config/
│   └── attribution_config.yaml          # Окна атрибуции, retention (30d), солевые параметры
├── web/
│   └── public/
│       └── swipies-tracker.js           # Клиентский JS-трекер (<3.5KB, zero deps)
├── src/
│   ├── __init__.py
│   ├── config.py                        # Pydantic Settings (чтение .env, соли, таймаутов)
│   ├── tracker_service.py               # Изолированный Flask-сервис приёма событий (порт 5001)
│   ├── models/                          # Строгие Pydantic DTO модели данных
│   │   ├── __init__.py
│   │   ├── events.py                    # RawEventDTO, HeartbeatDTO, PageViewDTO
│   │   ├── attribution.py               # AttributionRecordDTO, PaymentAttributionDTO
│   │   └── reports.py                   # RoasReportDTO, CplReportDTO, ChannelSummaryDTO
│   ├── core/                            # Бизнес-логика и аналитический процессинг
│   │   ├── __init__.py
│   │   ├── anonymizer.py                # SHA256(IP + Daily_Salt) + GeoIP resolver
│   │   ├── matcher.py                   # Алгоритмы First-Touch и Last-Touch атрибуции
│   │   ├── metrics_engine.py            # Расчет CAC, CPL, ROAS в Decimal
│   │   └── retention_guard.py           # Ежесуточная агрегация и purge событий >30 дней
│   ├── storage/                         # Слой персистентности и работы с БД
│   │   ├── __init__.py
│   │   ├── base.py                      # IAttributionRepository (интерфейс)
│   │   ├── sqlite_events_repo.py        # Репозиторий локальных событий сайта (WAL)
│   │   └── mysql_readonly_client.py     # Клиент к v_attribution_payments (read-only)
│   └── cli.py                           # Точка входа CLI (отчеты, аудит, purge)
├── deploy/
│   ├── nginx_attribution.conf           # Конфигурация Nginx (rate-limit 30r/s, proxy 5001)
│   └── swipies-tracker.service          # Systemd unit для изолированного Gunicorn-процесса
└── tests/                               # TDD-набор тестов с покрытием Edge Cases
    ├── __init__.py
    ├── conftest.py                      # Фикстуры in-memory DB, тестовых сессий и оплат
    ├── test_tracker_js_contract.py      # Валидация контракта данных swipies-tracker.js
    ├── test_anonymizer_ip.py            # Тесты: необратимость хэширования, ротация соли
    ├── test_payment_migration_diff.py   # Верификация DDL миграции и нуллабельности
    ├── test_view_readonly_isolation.py  # Проверка прав: запрет сырого SELECT и DML
    ├── test_attribution_models.py       # Тест First-Touch vs Last-Touch на сложных цепочках
    ├── test_retention_purge.py          # Тест удаления 35-дневных логов с сохранением summary
    ├── test_metrics_decimal_precision.py# Проверка отсутствия float-багов при расчете ROAS
    ├── test_codebase_allowlist_scan.py  # AST-сканер: запрет импорта из atmos/ и чтения .env
    └── test_e2e_traffic_to_payment.py   # Сквозной интеграционный тест: Клик -> Трекер -> Оплата
```

---

## 3. Матрица тестирования граничных случаев (Edge Cases Coverage)

| Модуль | Сценарий (Edge Case) | Ожидаемое поведение системы | Тестовый файл |
| :--- | :--- | :--- | :--- |
| **Tracker JS** | Пользователь заблокировал cookie / Incognito | Переход на `sessionStorage`. Если хранилище недоступно, генерируется одноразовый in-memory ID без падения скрипта. | `test_tracker_js_contract.py` |
| **Tracker JS** | Вкладка осталась открытой на ночь в фоне | `document.visibilityState === 'hidden'`. Таймер активного времени на паузе, heartbeat не накручивает `active_time_seconds`. | `test_tracker_js_contract.py` |
| **Ingestion API** | Спайк невалидного JSON или XSS в `utm_campaign` | Pydantic-валидатор отсекает тело запроса (HTTP 422), логирует `INVALID_PAYLOAD`, не роняя процесс воркера. | `test_tracker_js_contract.py` |
| **IP Anonymizer** | Заголовок `X-Forwarded-For` содержит список прокси: `1.2.3.4, 10.0.0.1` | Извлекается строго левый публичный клиентский IP (`1.2.3.4`), валидируется regex, хэшируется с солью. | `test_anonymizer_ip.py` |
| **IP Anonymizer** | Наступила полночь (00:00:01 UTC) — смена `Daily_Salt` | Хэширование переключается на соль текущего дня без сбоев или блокировок в памяти. | `test_anonymizer_ip.py` |
| **Payment Flow** | Оплата без `session_id` (прямой заход, AdBlock, стёрта cookie) | `session_id` в `payment_transaction` пишется как `NULL`. Платёж проходит 100% успешно; в отчёте атрибутируется как `DIRECT_ORGANIC`. | `test_payment_migration_diff.py` |
| **Payment Flow** | Сбой сети / timeout трекера во время оформления заказа | Клиентский чекаут не ждёт трекер: таймаут промиса 300ms, форма оплаты открывается штатно. | `test_e2e_traffic_to_payment.py` |
| **DB Isolation** | Попытка выполнить `SELECT gateway_response FROM payment_transaction` | MySQL возвращает `ERROR 1142: SELECT command denied to user 'analytics_ro'`. | `test_view_readonly_isolation.py` |
| **DB Isolation** | Запрос аналитики завис из-за сканирования большой выборки | Срабатывает `max_execution_time = 3000ms`, MySQL серверно обрывает запрос с кодом 3024, не перегружая боевую БД. | `test_view_readonly_isolation.py` |
| **Attribution** | Цепочка: Клик A (День 1) $\rightarrow$ Клик B (День 5) $\rightarrow$ Оплата | `First-Touch` относит 100% чека к Кампании A; `Last-Touch` относит 100% чека к Кампании B. | `test_attribution_models.py` |
| **Attribution** | Клик A (День 1) $\rightarrow$ Оплата через 35 дней | 30-дневная cookie истекла: First-Touch атрибутируется к `DIRECT_EXPIRED`, предотвращая ложную атрибуцию устаревшим кликам. | `test_attribution_models.py` |
| **Retention** | В БД присутствуют записи возрастом 1 день, 29 дней и 35 дней | Запуск `retention_guard`: записи возрастом 35 дней удалены; записи 1 и 29 дней сохранены; `daily_attribution_summary` не повреждена. | `test_retention_purge.py` |
| **Financials** | Расчёт ROAS при расходе $13.33 и выручке 500 000 UZS по курсу 12 800 | Расчёт через `Decimal`: точное значение без погрешностей `0.0000000000000001`. | `test_metrics_decimal_precision.py` |
| **Security Scan** | В коде аналитического модуля случайно появился `import atmos` или чтение `.env` | AST-сканер тестов `test_codebase_allowlist_scan.py` аварийно завершает CI/тест-сьют с кодом 1. | `test_codebase_allowlist_scan.py` |

---

## 4. Поэтапный план реализации (5 фаз разработки)

### Фаза 1: Слой БД, DDL миграция и безопасность прав (Zero-Trust)
1. Подготовка файла аддитивной миграции `migrations/V1.5__add_attribution_utm_columns.sql`.
2. Подготовка файла создания безопасного View `migrations/V1.6__create_v_attribution_payments.sql` с плейсхолдером `{{PAYER_HASH_SALT}}` и фильтром `WHERE pt.status = 'PAID'`.
3. Подготовка DDL для локальной базы событий `migrations/V1.7__create_attribution_events.sql` (`attribution_raw_events`, `daily_attribution_summary`).
4. Разработка тестов `test_payment_migration_diff.py` и `test_view_readonly_isolation.py`.
5. Реализация безопасного клиента `src/storage/mysql_readonly_client.py` с ограничением `max_execution_time`.

### Фаза 2: Frontend JS-трекер и модуль анонимизации данных
1. Разработка компактного `web/public/swipies-tracker.js` (<3.5 КБ, парсинг URL, cookie 30 дней, `sessionStorage`, `Page Visibility API`, `navigator.sendBeacon`).
2. Разработка `src/core/anonymizer.py` (суточное ротационное хэширование SHA256 с солью, GeoIP резолвер страны/города, немедленное стирание сырого IP).
3. Pydantic-модели валидации входящих событий `src/models/events.py`.
4. Написание и прогон тестов `test_tracker_js_contract.py` и `test_anonymizer_ip.py`.

### Фаза 3: Изолированный Ingestion Service и Storage с ранним Purge (Flask на порту 5001)
1. Разработка независимого Flask-сервиса `src/tracker_service.py` (`POST /api/v1/track/event`, обработка батчей, rate-limiting).
2. Реализация SQLite-репозитория `src/storage/sqlite_events_repo.py` с WAL-режимом, пулом транзакций и **встроенным методом ранней очистки `purge_expired_raw_events()`**.
3. Реализация легковесного CLI-скрипта очистки `src/core/retention_guard.py` уже на Фазе 3 (для гарантии от разрастания SQLite WAL до перехода к Фазе 4).
4. Подготовка конфигурации `deploy/nginx_attribution.conf` (upstream на `127.0.0.1:5001`, `limit_req`, таймаут 1s) и `deploy/swipies-tracker.service`.
5. Интеграционные тесты приёма событий и автоматического удаления записей >30 дней.

### Фаза 4: Движок сквозной атрибуции и интеграция с платежами
1. Разработка `src/core/matcher.py` (сопоставление транзакций из `v_attribution_payments` с событиями сессий по `session_id` и `utm_*` для моделей First-Touch и Last-Touch).
2. Разработка `src/core/metrics_engine.py` (вычисление CAC, CPL, ROAS, конверсий с защитой точности через `Decimal`).
3. Разработка расширенной агрегации витрин в `retention_guard.py` (сворачивание исторических метрик в `daily_attribution_summary` перед purge).
4. Прогон тестов `test_attribution_models.py`, `test_retention_purge.py`, `test_metrics_decimal_precision.py`.

### Фаза 5: CLI-интерфейс, Allow-List аудит и сквозной E2E
1. Разработка CLI в `src/cli.py`:
   * `attribution-report --from YYYY-MM-DD --to YYYY-MM-DD [--model first-touch|last-touch]`
   * `export --format csv|json`
   * `purge-old-events`
   * `audit-security`
2. Разработка AST-линтера `tests/test_codebase_allowlist_scan.py` для контроля Allow-list/Deny-list.
3. Разработка сквозного теста `tests/test_e2e_traffic_to_payment.py`.

---

## 5. Строгая последовательность контрольных гейтов (Hard Safety Gates)

```
[1. Локальная разработка модулей + Unit тесты]
                      ↓
[🛑 GATE 1: DB & Migration Safety Gate]
   • Миграция V1.5 протестирована на копии схемы: не блокирует таблицу, поля строго NULLABLE.
   • Тест прав: пользователь analytics_ro физически НЕ МОЖЕТ прочитать gateway_response,
     account_email или выполнить INSERT/UPDATE.
   • Соль {{PAYER_HASH_SALT}} подставляется строго на этапе миграции, не светится в гите.
                      ↓
[🛑 GATE 2: Process Isolation & Blast Radius Gate (Числовые пороги)]
   • Сервис трекинга запущен на порту 127.0.0.1:5001 в отдельном процессе Gunicorn (swipies-tracker.service).
   • Синтетический стресс-тест: 100 req/sec в течение 60 секунд на эндпоинт трекинга (порт 5001).
   • ЖЁСТКИЕ ЧИСЛОВЫЕ КРИТЕРИИ ПРИЁМКИ ДЛЯ ПОРТА 5000 (Платежи):
     1. Latency: p95 задержка запросов к платёжным роутам (/api/pay/*) не увеличивается более чем на +15 мс (отклонение p95 <= 20% от базовой линии покоя).
     2. Error Rate: уровень ошибок платёжного ядра строго 0.00% (0 сброшенных или 5xx соединений).
     3. Resource Capping: потребление ОЗУ трекинг-процессом <= 200 MB RSS; CPU <= 50% (гарантируя минимум 50% CPU для платежей).
   • Nginx сбрасывает зависшие трекинг-клиенты строго по таймауту 1s, не удерживая воркеры.
                      ↓
[🛑 GATE 3: Privacy & Zero-Trust Payment Flow Gate]
   • В логах и таблицах БД отсутствуют сырые IP-адреса (только хэш с солью и город/страна).
   • Проброс session_id в system_api.py проверен diff-ревью: новые поля не участвуют
     в проверке подписей, расчёте сумм и GET_LOCK.
                      ↓
[🛑 GATE 4: Full E2E Attribution Clearance Gate]
   • Сквозной прогон симуляции:
     Клик Meta UTM -> Сбор трекером -> Запись события -> Оплата в MySQL -> Генерация отчёта.
   • Сверка расчётов ROAS и CAC с ручным калькулятором (с точностью до сума).
   • Тест AST-сканера подтверждает чистоту репозитория от секретов Atmos/.env.
```

---

## 6. Детальный Zero-Trust Diff для `system_api.py`

Для прозрачности и исключения скрытых изменений платёжного кода, фиксируется точный план минимального diff для проброса атрибуции:

### 6.1 Разделение зон ответственности (Route vs Service)
Критический вопрос безопасности: `PaymentTransactionService.create_pending()` вызывается внутри блока блокировки `GET_LOCK(transaction_id, 10)` при проверке `if not existing_tx:`. Увеличение времени удержания лока недопустимо.

Поэтому устанавливается строгий контракт:
1. **Вся валидация и regex-очистка производятся ДО входа в критическую секцию** (на уровне Flask-роута `/api/pay/apply`).
2. **Внутри `create_pending()` новые поля являются ЧИСТЫМИ PASSTHROUGH-значениями** — они просто добавляются как готовые именованные параметры в существующий параметризованный SQL `INSERT`.
3. **Нулевой оверхед на `GET_LOCK`:** Никаких регулярных выражений, сетевых вызовов или валидаций внутри сервисного метода. Дополнительное время удержания лока составляет $\approx 0$ микросекунд.
4. **Идемпотентность не затронута:** Проверка `if not existing_tx:` и поиск существующей транзакции работают ровно так же, как в Треке 2.

### 6.2 План минимального diff

```python
# ==============================================================================
# 1. system_api.py (Уровень роута — ДО вызова сервиса и ДО захвата лока)
# ==============================================================================
# Извлечение опциональных метаданных атрибуции:
session_id = request.json.get('session_id')
utm_data = request.json.get('utm', {})

# Санитарная очистка ВНЕ критической секции (Строгий regex, обрезка длины):
clean_session_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(session_id))[:64] if session_id else None
clean_utm_source = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(utm_data.get('utm_source', '')))[:64] or None
clean_utm_medium = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(utm_data.get('utm_medium', '')))[:64] or None
clean_utm_campaign = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(utm_data.get('utm_campaign', '')))[:128] or None
clean_utm_content = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(utm_data.get('utm_content', '')))[:128] or None
clean_utm_term = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(utm_data.get('utm_term', '')))[:128] or None

# ==============================================================================
# 2. payment_service.py (Внутри критической секции GET_LOCK — ЧИСТЫЙ PASSTHROUGH)
# ==============================================================================
# def create_pending(..., session_id=None, utm_source=None, utm_medium=None, 
#                    utm_campaign=None, utm_content=None, utm_term=None):
#     if not existing_tx:
#         cursor.execute("""
#             INSERT INTO payment_transaction (
#                 ..., session_id, utm_source, utm_medium, utm_campaign, utm_content, utm_term
#             ) VALUES (
#                 ..., :session_id, :utm_source, :utm_medium, :utm_campaign, :utm_content, :utm_term
#             )
#         """, {..., 'session_id': session_id, 'utm_source': utm_source, ...})

# ВАЖНО: Расчёт сумм, валидация Atmos и GET_LOCK не меняются ни на один байт!
```

---

## 7. ГЕЙТ 2: Вопросы согласования перед переходом к TASKS.md

1. Утверждается ли разделение на 5 фаз реализации с 4 обязательными промежуточными гейтами?
2. Согласован ли состав Edge Cases (особенно обработка блокировщиков рекламы, фоновых неактивных вкладок и таймаутов БД)?
3. Принимается ли план минимального diff для `system_api.py`?
