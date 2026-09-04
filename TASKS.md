# SWIPIES Traffic Attribution & Analytics — Task Checklist (Phase 3: Tasks)

**Version:** 1.0.0  
**Status:** PROPOSED (GATE 3 REVIEW — Human Approval Required)  
**Track:** Track 3 (Traffic Attribution & Analytics)  
**Methodology:** SpecKit Workflow (Risk-Ordered, Atomic Tasks, Hard Safety Gates)

---

## 1. Структура атомарных задач по блокам

### Блок 1: Окружение, Pydantic DTO и локальное хранилище с ранним Purge (Risk Order: 1)
- [x] **TASK-1.1:** Настроить конфигурацию проекта: `.gitignore`, `.env.example`, `requirements.txt` (изоляция секретов, зависимости: `flask`, `gunicorn`, `pydantic>=2.0`, `typer`, `tabulate`, `pytest`, `freezegun`).
- [x] **TASK-1.2:** Разработать строгие Pydantic DTO-модели (`src/models/events.py`, `src/models/attribution.py`, `src/models/reports.py`):
  * `RawEventDTO`: `session_id`, `event_type`, `page_url`, `page_path`, `active_time_seconds`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `referrer`.
  * `PaymentAttributionDTO`: `payment_id`, `transaction_id`, `amount_uzs`, `status`, `session_id`, `utm_*`, `masked_payer_hash`.
  * `RoasReportDTO`, `CplReportDTO`, `ChannelSummaryDTO` с финансовыми полями в типе `Decimal`.
- [x] **TASK-1.3:** Разработать DDL локальной БД SQLite `migrations/V1.7__create_attribution_events.sql` (таблицы `attribution_raw_events` и `daily_attribution_summary` с индексами по `session_id`, `created_at`, `utm_campaign`).
- [x] **TASK-1.4:** Реализовать `SqliteEventsRepository` (`src/storage/sqlite_events_repo.py`) с поддержкой режима WAL, пулом соединений и пакетной вставкой событий.
- [x] **TASK-1.5:** Реализовать ранний механизм очистки логов (`src/core/retention_guard.py`): метод `purge_expired_raw_events(retention_days=30)` для предотвращения разрастания SQLite с первого дня сбора данных.
- [x] **TASK-1.6:** Написать Unit-тест `tests/test_retention_purge.py` (с фикстурой `freezegun`: проверка удаления записей возрастом 35 дней и сохранения записей младше 30 дней).
  * *Критерий верификации:* `pytest tests/test_retention_purge.py -v` (зелёный).

### 🛑 КОНТРОЛЬНАЯ ТОЧКА А (Checkpoint A — Storage & Purge Ready):
> **Отчёт человеку:** Предъявить схему DDL локальной БД, код раннего purge и результат прогона `test_retention_purge.py`.

---

### Блок 2: Аддитивная миграция БД и Zero-Trust проброс в `system_api.py` (Критический блок платёжного ядра — Risk Order: 2)
> ⚠️ **ВНИМАНИЕ:** Единственный блок трека, затрагивающий боевое платёжное ядро. Выделен в изолированную задачу со строгой верификацией инвариантов.

- [x] **TASK-2.1:** Подготовить файл аддитивной SQL-миграции `migrations/V1.5__add_attribution_utm_columns.sql`:
  * Добавление полей `session_id VARCHAR(64) NULL`, `utm_source VARCHAR(64) NULL`, `utm_medium VARCHAR(64) NULL`, `utm_campaign VARCHAR(128) NULL`, `utm_content VARCHAR(128) NULL`, `utm_term VARCHAR(128) NULL` в таблицу `payment_transaction`.
  * Добавление индексов `idx_pt_session_id` и `idx_pt_utm_campaign`.
- [x] **TASK-2.2:** Подготовить DDL безопасного представления `migrations/V1.6__create_v_attribution_payments.sql`:
  * `CREATE OR REPLACE VIEW v_attribution_payments` со строгим фильтром `WHERE pt.status = 'PAID'`.
  * Плейсхолдер соли `{{PAYER_HASH_SALT}}` для генерации `masked_payer_hash`.
  * Исключение полей `gateway_response`, `account_email`, данных карт и системных заметок.
- [x] **TASK-2.3:** Написать Unit-тест прав доступа `tests/test_view_readonly_isolation.py`:
  * Проверка `SELECT * FROM v_attribution_payments` под юзером `analytics_ro` (успешно).
  * Попытка `SELECT gateway_response FROM payment_transaction` $\rightarrow$ проверка ошибки `ERROR 1142: SELECT command denied`.
  * Попытка любого `INSERT/UPDATE/DELETE` $\rightarrow$ проверка отказа в доступе.
- [x] **TASK-2.4:** Подготовить минимальный diff для роута `/api/pay/apply` в `system_api.py`:
  * Извлечение `session_id` и `utm` из входящего `request.json`.
  * Строгая regex-очистка и обрезка длины строк **ДО входа в критическую секцию**.
- [x] **TASK-2.5:** Подготовить минимальный diff для `PaymentTransactionService.create_pending()`:
  * Добавление опциональных аргументов `session_id=None`, `utm_source=None` и т.д.
  * Чистый passthrough в параметры SQL `INSERT` без дополнительной валидации внутри метода.
  * Полное сохранение нетронутыми проверки `if not existing_tx:` и удержания `GET_LOCK`.
- [x] **TASK-2.6:** Написать интеграционный тест `tests/test_payment_flow_zero_impact.py`:
  * Создание платежа с переданными UTM-параметрами $\rightarrow$ поля записаны в БД, платёж в статусе `PENDING`.
  * Создание платежа без UTM $\rightarrow$ поля записаны как `NULL`, платёж в статусе `PENDING`.
  * Проверка: расчёт сумм (`expected_amount_uzs`), генерация подписи Atmos и время удержания `GET_LOCK` не изменились.
  * *Критерий верификации:* `pytest tests/test_payment_flow_zero_impact.py -v` (зелёный).

### 🛑 КОНТРОЛЬНАЯ ТОЧКА Б (Checkpoint B — Payment Core Zero-Trust Review):
> **Отчёт человеку:** Предъявить изолированный git diff для `system_api.py` и `PaymentTransactionService`, результаты тестов прав View и отсутствия влияния на платёжное ядро. **Без явного подтверждения человека код в прод не вливается.**

---

### Блок 3: Frontend JS-трекер и Анонимизация IP (Risk Order: 3)
- [x] **TASK-3.1:** Разработать компактный клиентский скрипт `web/public/swipies-tracker.js`:
  * Размер < 3.5 КБ gzip, vanilla JS (zero dependencies).
  * Парсинг query-параметров URL (`utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `fbclid`).
  * Сохранение в `sessionStorage` (текущая сессия) и cookie `_swp_utm` (First-Touch, срок 30 дней).
  * Подсчёт реального активного времени через `document.visibilityState === 'visible'` (фоновые вкладки на паузе).
  * Отправка событий `page_view`, `heartbeat` (каждые 30 сек) и финального сброса через `navigator.sendBeacon`.
  * Fallback при блокировке cookies/инкогнито: сохранение в in-memory state без ошибок в консоли браузера.
- [x] **TASK-3.2:** Реализовать модуль анонимизации данных `src/core/anonymizer.py`:
  * Извлечение левого публичного IP из заголовка `X-Forwarded-For` с валидацией regex.
  * Вычисление `SHA256(IP + Daily_Salt)` с суточной ротацией соли в 00:00 UTC.
  * Локальный GeoIP резолвер (определение `country="UZ"`, `city="Tashkent"`).
  * Гарантированное удаление сырого IP из памяти без сохранения в лог или БД.
- [x] **TASK-3.3:** Написать Unit-тесты `tests/test_tracker_js_contract.py` и `tests/test_anonymizer_ip.py`:
  * Проверка JSON-контракта полезной нагрузки трекера.
  * Проверка необратимости хэширования IP (невозможность восстановить исходный адрес).
  * Проверка корректной ротации соли в полночь без коллизий.
  * *Критерий верификации:* `pytest tests/test_tracker_js_contract.py tests/test_anonymizer_ip.py -v` (зелёный).

---

### Блок 4: Изолированный Ingestion Service (Flask на порту 5001) и Nginx (Risk Order: 4)
- [x] **TASK-4.1:** Разработать независимый Flask-сервис `src/tracker_service.py`:
  * Роут `POST /api/v1/track/event` (приём батчей событий, валидация через `RawEventDTO`).
  * Анонимизация IP на лету и сохранение в `SqliteEventsRepository`.
  * Роут `GET /health` для мониторинга доступности.
- [x] **TASK-4.2:** Подготовить конфигурационный файл Nginx `deploy/nginx_attribution.conf`:
  * Определение зоны rate-limiting `limit_req_zone $binary_remote_addr zone=track_limit:10m rate=30r/s;`.
  * Блок `location /api/v1/track/` с проксированием на `127.0.0.1:5001`, `burst=20 nodelay` и таймаутом `1s`.
  * Блок `location /api/pay/` с проксированием на `127.0.0.1:5000` (платёжное ядро).
- [x] **TASK-4.3:** Подготовить Systemd-юнит `deploy/swipies-tracker.service`:
  * Запуск Gunicorn с сервисом трекинга на порту `127.0.0.1:5001`.
  * Аппаратные лимиты: `MemoryMax=256M`, `CPUQuota=50%`, `Restart=always`.
- [x] **TASK-4.4:** Разработать нагрузочный тест изоляции процессов (Synthetic Baseline) `tests/test_process_isolation_stress.py`:
  * Синтетическая нагрузка: 100 req/sec на порт 5001 в течение 60 секунд.
  * Замер влияния на эмулятор порта 5000 (лабораторный baseline):
    1. $p95$ задержка платёжных роутов увеличивается не более чем на **+15 мс** ($\Delta \le 20\%$). Факт: -7.35 мс (в пределах шума).
    2. Уровень ошибок платежей: строго **0.00%**. Факт: 0.00%.
    3. Потребление памяти процессом трекинга $\le 200\text{ МБ RSS}$. Факт: 95.37 МБ.
  * *Критерий верификации:* `pytest tests/test_process_isolation_stress.py -v` (зелёный).
- [ ] **TASK-4.5:** Обязательный стресс-тест на staging/боевом стеке (Порт 5000 реального Flask/Gunicorn vs Порт 5001):
  * **Хард-гейт перед слиянием в `swipies_26`:** Запуск реального ядра `system_api.py` на порту 5000 с боевым подключением к MySQL (или staging-базе) параллельно со стрессом 100 req/s на порт 5001.
  * Проверка отсутствия конкуренции за GIL, сетевые дескрипторы и CPU ядра ОС.
  * Выполняется перед Checkpoint D / финальным релизом.

### 🛑 КОНТРОЛЬНАЯ ТОЧКА В (Checkpoint C — Gate 2 Baseline & Staging Gate):
> **Статус:** Лабораторный baseline сдан (TASK-4.4). Допуск к разработке Блоков 5 и 6 открыт. Окончательное закрытие Gate 2 для продакшн-деплоя привязано к TASK-4.5 перед слиянием в `swipies_26`.


---

### Блок 5: Движок сквозной атрибуции и метрик (Risk Order: 5)
- [x] **TASK-5.1:** Реализовать клиент к БД `src/storage/mysql_readonly_client.py`:
  * Подключение под пользователем `analytics_ro` на `127.0.0.1`.
  * Автоматическое выполнение `SET SESSION max_execution_time = 3000;` при открытии сессии.
  * Чтение данных строго из View `v_attribution_payments` с фильтрацией по диапазону дат.
- [x] **TASK-5.2:** Реализовать движок сопоставления сессий `src/core/matcher.py`:
  * Модель **First-Touch**: привязка оплаты к первому зарегистрированному источнику за 30 дней (по cookie `_swp_utm`).
  * Модель **Last-Touch**: привязка оплаты к источнику последней сессии перед оплатой.
  * Обработка прямых оплат без сессий: маркировка как `DIRECT_ORGANIC`.
- [x] **TASK-5.3:** Реализовать модуль финансовой аналитики `src/core/metrics_engine.py`:
  * Расчёт показателей: Visits, Leads, Paying Customers, Conversion Rate, Revenue UZS, CAC, CPL, ROAS.
  * Использование типа `Decimal` с банковским округлением `ROUND_HALF_UP` (защита от float-погрешностей).
- [x] **TASK-5.4:** Доработать `src/core/retention_guard.py`:
  * Ежесуточное агрегирование сырых событий в витрину `daily_attribution_summary` перед удалением.
- [x] **TASK-5.5:** Написать Unit-тесты `tests/test_attribution_models.py` и `tests/test_metrics_decimal_precision.py`:
  * Тест цепочек: Клик A $\rightarrow$ Клик B $\rightarrow$ Оплата (проверка корректного распределения выручки).
  * Тест точности формул ROAS и CAC на дробных суммах.
  * *Критерий верификации:* `pytest tests/test_attribution_models.py tests/test_metrics_decimal_precision.py -v` (зелёный).


---

### Блок 6: CLI-интерфейс, AST-аудит безопасности и сквозной E2E (Risk Order: 6)
- [ ] **TASK-6.1:** Реализовать CLI интерфейс `src/cli.py` (на базе `typer`):
  * `attribution-report --from YYYY-MM-DD --to YYYY-MM-DD [--model first-touch|last-touch]` (сводная таблица в консоли через `tabulate`).
  * `export --from YYYY-MM-DD --to YYYY-MM-DD --format csv|json --output path/to/file`.
  * `purge-old-events [--days 30]` (ручной вызов очистки).
  * `audit-security` (проверка прав и доступности).
- [ ] **TASK-6.2:** Разработать автоматический AST-сканер безопасности `tests/test_codebase_allowlist_scan.py`:
  * Рекурсивный парсинг абстрактного синтаксического дерева файлов каталога `src/`.
  * Проверка запрета импортов из `atmos payment system/` и `server/`.
  * Проверка отсутствия чтения `.env` или обращения к `docs/specs/`.
  * *Критерий верификации:* `pytest tests/test_codebase_allowlist_scan.py -v` (зелёный).
- [ ] **TASK-6.3:** Разработать сквозной E2E интеграционный тест `tests/test_e2e_traffic_to_payment.py`:
  * Имитация визита пользователя с UTM-метками Meta (`utm_source=meta&utm_campaign=b2b_fintech`).
  * Фиксация событий трекером и сохранение в SQLite.
  * Имитация успешной оплаты через mock `payment_transaction` с `session_id`.
  * Вызов `attribution-report` и сверка расчётов ROAS и CAC.
  * *Критерий верификации:* `pytest tests/test_e2e_traffic_to_payment.py -v` (зелёный).

### 🛑 КОНТРОЛЬНАЯ ТОЧКА Г (Checkpoint D — Final E2E Gate 4):
> **Отчёт человеку:** Предъявить полный отчёт выполнения `pytest` (100% тестов зелёные), отчёт AST-сканера чистоты кодовой базы и консольный вывод реального отчёта атрибуции.

---

## 2. Сводная матрица задач и верификации

| Блок | Основные задачи | Файлы тестов | Контрольная точка |
| :--- | :--- | :--- | :--- |
| **1. Окружение & Storage** | TASK-1.1 – TASK-1.6 | `test_retention_purge.py` | 🛑 Checkpoint A |
| **2. Платёжное ядро (Zero-Trust)** | TASK-2.1 – TASK-2.6 | `test_payment_migration_diff.py`, `test_view_readonly_isolation.py`, `test_payment_flow_zero_impact.py` | 🛑 Checkpoint B (Human Review) |
| **3. Tracker JS & IP Anonymizer** | TASK-3.1 – TASK-3.3 | `test_tracker_js_contract.py`, `test_anonymizer_ip.py` | — |
| **4. Ingestion Service (5001)** | TASK-4.1 – TASK-4.4 | `test_process_isolation_stress.py` | 🛑 Checkpoint C (Gate 2) |
| **5. Движок атрибуции** | TASK-5.1 – TASK-5.5 | `test_attribution_models.py`, `test_metrics_decimal_precision.py` | — |
| **6. CLI & Сквозной E2E** | TASK-6.1 – TASK-6.3 | `test_codebase_allowlist_scan.py`, `test_e2e_traffic_to_payment.py` | 🛑 Checkpoint D (Gate 4) |
