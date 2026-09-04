# SWIPIES Traffic Attribution & Analytics — Functional Specification (Track 3)

**Version:** 1.1.0  
**Project:** Web Traffic Attribution, Meta UTM Tracking & Revenue Analytics  
**Track:** Track 3 (Traffic Attribution & Analytics)  
**Author:** AI Systems Architect (SpecKit Workflow)  
**Status:** DRAFT FOR HUMAN REVIEW (GATE 1 - REVISED)

---

## 1. Executive Summary & WHY (Бизнес-контекст и цели)

В треках рекламы (Meta Ads Automation) и продаж SWIPIES критически важно замкнуть цепочку между **затратами на маркетинг** и **реальными поступлениями на расчетный счет**:

```
[Реклама Meta: Instagram/FB] 
       ↓ (Клик с UTM-метками: utm_source=meta, utm_campaign=b2b_banking, fbclid=...)
[Целевая страница сайта SWIPIES]
       ↓ (swipies-tracker.js: фиксация UTM, реферера, страниц, активного времени)
[Ingestion API: Flask Blueprint POST /api/v1/track/event]
       ↓ (Анонимизация IP на лету, валидация, сброс в локальную таблицу attribution_raw_events)
[Пользователь переходит к оплате тарифа (checkout modal)]
       ↓ (session_id и utm передаются через /api/pay/apply в PaymentTransactionService)
[Создание транзакции в payment_transaction с привязанными session_id и utm_*]
       ↓ (Оплата через Atmos в сумах UZS с верификацией и GET_LOCK)
[Attribution Engine: Read-Only связь через MySQL View v_attribution_payments]
       ↓
[Сводный отчёт: Реальный CAC, CPL, ROAS, конверсия клика в оплату]
```

### Главные архитектурные принципы
1. **Security-First & Privacy-by-Design**: Аналитический агент изолирован от платежных модулей, банковских ключей Atmos и сырых конфиденциальных данных клиентов.
2. **Zero-Trust к изменениям платежного ядра**: Добавление атрибуции в платёжную таблицу `payment_transaction` выполняется строго аддитивной, проверенной миграцией без изменения логики валидации платежей, списаний и расчёта сумм.
3. **Единый стек (Flask), но физически изолированный процесс (Blast Radius Isolation)**: Никаких вторых фреймворков (FastAPI/LiteStar) на одном сервере, но трекинг запускается как **отдельный OS-процесс Gunicorn/systemd (`swipies-tracker.service` на порту 5001)**. Публичный трафик физически не делит воркеры, память и процессорное время с платёжным бэкендом (`swipies-api.service` на порту 5000).
4. **Прямой локальный Read-Only доступ к БД**: Пользователь `analytics_ro` подключается напрямую к локальной боевой MySQL (`127.0.0.1`), но ограничен чтением единственного защищенного View с аппаратным `max_execution_time`.

---

## 2. Источники данных и технический механизм сбора

| Параметр данных | Описание и состав | Конкретный технический источник (Не абстрактно) |
| :--- | :--- | :--- |
| **1. Маркетинговые метки (UTM & Click ID)** | `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, а также `fbclid` (Meta Click ID). | **Frontend JS SDK (`swipies-tracker.js`):**<br>• При загрузке страницы парсит `window.location.search`.<br>• Сохраняет объект меток в `sessionStorage` (для текущей сессии) и cookie `_swp_utm` (срок жизни: 30 дней, атрибуция First-Touch).<br>• Генерирует уникальный `session_id` (UUID v4) при первом визите. |
| **2. Посещённые страницы и глубина визита** | `page_url`, `page_path`, `page_title`, `referrer_url`, признак входа/выхода. | **Frontend JS SDK (`swipies-tracker.js`):**<br>• Слушает событие `DOMContentLoaded` для классических страниц.<br>• Перехватывает вызовы History API (`history.pushState`, событие `popstate`) для SPA-переходов без перезагрузки.<br>• Отправляет событие `event_type="page_view"`. |
| **3. Время на сайте (Time-on-site) и вовлечение** | `active_time_seconds`, `scroll_depth_percent`. | **Frontend JS SDK (`swipies-tracker.js`):**<br>• Учитывается **только активное время** (проверка `document.visibilityState === 'visible'` и пользовательской активности). Фоновые неактивные вкладки не накручивают счетчик.<br>• Heartbeat-пинг каждые 30 секунд + финальный сброс через `navigator.sendBeacon` при закрытии/скрытии страницы (`pagehide` / `visibilitychange`). |
| **4. Серверный транспорт и инжестия** | Приём батчей событий, валидация схемы, фиксация User-Agent (устройство/ОС). | **Изолированный Flask-сервис (`POST /api/v1/track/event`):**<br>• Работает как отдельный легковесный Gunicorn-процесс на порту `127.0.0.1:5001`.<br>• Nginx выполняет reverse proxy с жестким rate-limiting (`limit_req zone=track_limit burst=20 nodelay`) и таймаутом 1 сек.<br>• Бэкенд валидирует JSON, анонимизирует IP в памяти и пишет в таблицу `attribution_raw_events`. |
| **5. Конверсии и платежи** | Дата/время оплаты (`create_date`), сумма в сумах (`paid_amount_uzs`), валюта (`UZS`), статус, тариф (`plan_type`), `session_id`, `utm_*`. | **Read-Only MySQL View (`v_attribution_payments`):**<br>• Читается пакетным скриптом аналитики напрямую из боевой MySQL (`127.0.0.1`) через выделенного пользователя `analytics_ro`. |

> [!NOTE]
> **Почему выбран отдельный Tracking-эндпоинт вместо парсинга Nginx access logs:**
> 1. Nginx access log не видит реального активного времени (Time-on-site) и клиентских переходов внутри SPA без перезагрузки страницы.
> 2. Nginx access log по умолчанию пишет сырые IP-адреса на диск в открытом виде. Выделенный эндпоинт анонимизирует IP «на лету» в оперативной памяти до сброса в БД.

---

## 3. Схема БД и сквозной платёжный флоу (Data Architecture)

### 3.1 Реальная структура существующей таблицы `payment_transaction`
Из спецификации Трека 2 (v1.4) зафиксирована точная DDL-структура таблицы `payment_transaction`:
```text
id, transaction_id, user_id, tenant_id, account_email, plan_type, duration_months, 
expected_amount_uzs, paid_amount_uzs, status, payment_method, error_code, error_message, 
gateway_response, is_provisioned, provisioned_at, audit_note, create_date, update_date
```
*Валюта строго зафиксирована в архитектуре проекта:* **только UZS (узбекские сумы)**. Поля `currency` в таблице нет, суммы хранятся в `expected_amount_uzs` и `paid_amount_uzs`. Email плательщика хранится в поле `account_email`. Временные метки — `create_date` и `update_date`.

### 3.2 Под-шаг 1.1: Аддитивная миграция `payment_transaction`
Для связки трафика с платежами требуется **строго аддитивная** миграция, добавляющая нуллабельные поля атрибуции:

```sql
-- Миграция: V1.5__add_attribution_utm_columns.sql
-- БЕЗОПАСНОСТЬ: Все новые поля строго NULLABLE, без блокировки боевой таблицы
ALTER TABLE payment_transaction
    ADD COLUMN session_id VARCHAR(64) NULL AFTER status,
    ADD COLUMN utm_source VARCHAR(64) NULL AFTER session_id,
    ADD COLUMN utm_medium VARCHAR(64) NULL AFTER utm_source,
    ADD COLUMN utm_campaign VARCHAR(128) NULL AFTER utm_medium,
    ADD COLUMN utm_content VARCHAR(128) NULL AFTER utm_campaign,
    ADD COLUMN utm_term VARCHAR(128) NULL AFTER utm_content,
    ADD INDEX idx_pt_session_id (session_id),
    ADD INDEX idx_pt_utm_campaign (utm_campaign);
```

### 3.3 Zero-Trust проброс атрибуции через платёжный пайплайн

```
[Фронтенд: Checkout Modal]
    │  Извлекает session_id и UTM из cookie '_swp_utm'
    ▼
POST /api/pay/apply  (JSON body: {..., "session_id": "...", "utm": {...}})
    │
    ▼
[system_api.py: @manager.route('/api/pay/apply')]
    │  1. Строгая санитарная фильтрация строк UTM (alphanumeric + safe chars, длина <= 128)
    │  2. Передача полей session_id, utm_* в PaymentTransactionService
    ▼
[PaymentTransactionService.create_pending()]
    │  INSERT INTO payment_transaction (..., session_id, utm_source, utm_campaign, ...)
    ▼
[БАНКОВСКИЙ ЭКВАЙРИНГ ATMOS]  <-- В Atmos UTM-метки НЕ ПЕРЕДАЮТСЯ (чистый платёжный протокол)
    │
    ▼
[Webhook / Callback: Atmos notify]
    │  Сверка подписи, статус PAID, применение GET_LOCK
    │  (Логика верификации и списания денег НЕ ТРОГАЕТСЯ И НЕ ИЗМЕНЯЕТСЯ)
    ▼
[payment_transaction: status='PAID']
    │  Транзакция завершена, поля session_id и utm_source уже сохранены на шаге create_pending
```

**Критические гарантии безопасности платёжного ядра:**
1. Поля атрибуции (`session_id`, `utm_*`) являются **чисто информационными метаданными**.
2. Они **ни при каких условиях не участвуют**:
   * в расчёте и проверке сумм (`expected_amount_uzs`, `paid_amount_uzs`),
   * в валидации криптографических подписей Atmos или хэшей транзакций,
   * в правилах блокировки `GET_LOCK(transaction_id, 10)`.
3. Любая ошибка валидации или парсинга UTM на фронтенде/бэкенде **не блокирует платёж**: если `session_id` отсутствует или повреждён, поля записываются как `NULL`, а платёж обрабатывается штатно.

---

## 4. Доступ к базе данных: выделенный Read-Only DB-юзер и View

### 4.1 Решение по модели подключения к БД
* **Выбор для v1:** **Прямое подключение к боевой СУБД MySQL (`127.0.0.1`)** под выделенным пользователем `analytics_ro`.
* **Обоснование:**
  1. Вся инфраструктура на текущем этапе размещена на одном сервере, выделенной физической реплики БД нет.
  2. Риск деградации боевой базы исключается аппаратным ограничением сессии:
     `SET SESSION max_execution_time = 3000;` (принудительное прерывание любого запроса аналитики дольше 3 секунд).
  3. Чтение выполняется исключительно пакетными запросами по индексу `(create_date, status)` в ночное время (02:00 UTC) либо по явному вызову CLI.

### 4.2 Безопасное представление (View)
Пользователь `analytics_ro` **не имеет доступа к таблице `payment_transaction` напрямую**. Доступ открыт только к View:

```sql
CREATE OR REPLACE VIEW swipies_db.v_attribution_payments AS
SELECT 
    pt.id AS payment_id,
    pt.transaction_id AS transaction_id,
    pt.create_date AS payment_time,
    pt.paid_amount_uzs AS amount_uzs,
    'UZS' AS currency,
    pt.status AS payment_status,
    pt.plan_type AS plan_type,
    pt.session_id AS session_id,
    pt.utm_source AS utm_source,
    pt.utm_medium AS utm_medium,
    pt.utm_campaign AS utm_campaign,
    pt.utm_content AS utm_content,
    pt.utm_term AS utm_term,
    -- Псевдоанонимизированный хэш аккаунта с солью (для подсчёта повторных оплат без раскрытия email):
    SHA2(CONCAT(pt.account_email, '{{PAYER_HASH_SALT}}'), 256) AS masked_payer_hash
FROM swipies_db.payment_transaction pt
WHERE pt.status = 'PAID';
```

```sql
-- Создание ограниченного пользователя:
CREATE USER 'analytics_ro'@'127.0.0.1' IDENTIFIED BY 'STRONG_RANDOM_RO_PASSWORD';
GRANT SELECT ON swipies_db.v_attribution_payments TO 'analytics_ro'@'127.0.0.1';
FLUSH PRIVILEGES;
```

> [!IMPORTANT]
> **Управление солью `{{PAYER_HASH_SALT}}`:**
> Литерал соли **никогда не коммитится в репозиторий и спецификацию**. При применении миграции на сервере значение подставляется автоматически через переменную окружения `ATTRIBUTION_SALT` из Secret Manager / `.env` деплоя.

### 4.3 Гарантированно исключённые чувствительные поля
На уровне DDL View из доступа аналитики вырезаны:
* ❌ `gateway_response` (сырой ответ шлюза Atmos с техническими метаданными банка).
* ❌ Сырой `account_email` (заменён необратимым `masked_payer_hash`).
* ❌ `error_code`, `error_message`, `audit_note` (внутренние системные заметки).
* ❌ Данные банковских карт, токены и merchant-ключи.

---

## 5. Архитектура процессов и физическая изоляция (Blast Radius Containment)

### 5.1 Решение: Единый стек (Flask), но строго РАЗДЕЛЬНЫЕ OS-процессы
Публичный трафик трекинга (события кликов, скроллов, heartbeat) открыт всему интернету и потенциально подвержен всплескам трафика, флуду или ошибкам сериализации. Размещение трекинга внутри того же процесса, что и платёжный код, нарушило бы базовый принцип безопасности.

Поэтому трекинг реализуется на том же стеке **Flask**, но выносится в **отдельный независимый системный процесс**:

```
                                [INTERNET]
                                    │
                                    ▼
                          [Nginx Reverse Proxy]
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         │ location /api/v1/track/                             │ location /api/pay/
         │ (rate-limit: 30r/s, timeout: 1s)                    │ location /api/webhook/atmos
         ▼                                                     ▼
[swipies-tracker.service]                             [swipies-api.service]
Gunicorn Instance #2 (PID 4102)                       Gunicorn Instance #1 (PID 2814)
Port: 127.0.0.1:5001                                  Port: 127.0.0.1:5000
Modules: src.tracker_service:app                      Modules: system_api:app
DB Access: analytics_rw (attribution_raw_events)      DB Access: app_rw (payment_transaction, Atmos)
```

### 5.2 Преимущества физической изоляции процессов
1. **Изоляция сбоев (Blast Radius):** Утечка памяти, десериализационный баг, CPU-спайк или зависание трекингового воркера **физически не способны затронуть платёжное ядро**. Платёжные воркеры на порту 5000 продолжают обрабатывать платежи и вебхуки Atmos в штатном режиме.
2. **Нулевой overhead на рантайм:** Используется тот же самый Python virtualenv, те же библиотеки (`flask`, `gunicorn`, `pydantic`), без затягивания второго фреймворка.
3. **Раздельные лимиты ресурсов:** Через systemd для `swipies-tracker.service` задаются жесткие ограничения по памяти (`MemoryMax=256M`) и CPU (`CPUQuota=50%`), исключающие влияние на платежи.

### 5.3 Конфигурация Nginx Reverse Proxy
```nginx
# 1. Зона rate-limiting для публичного трекинга:
limit_req_zone $binary_remote_addr zone=track_limit:10m rate=30r/s;

# 2. Роутинг трекинга на порт 5001:
location /api/v1/track/ {
    limit_req zone=track_limit burst=20 nodelay;
    proxy_pass http://127.0.0.1:5001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    
    # Жесткий таймаут 1 секунда:
    proxy_connect_timeout 1s;
    proxy_read_timeout 1s;
    proxy_send_timeout 1s;
}

# 3. Роутинг платёжного ядра на порт 5000:
location /api/pay/ {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_connect_timeout 10s;
    proxy_read_timeout 10s;
}
```

---

## 6. Политика доступа к кодовой базе (Codebase Allow-List)

### 6.1 Allow-List (Разрешено агенту для чтения и модификации)
* `web/src/pages/` (или HTML-шаблоны сайта `index.html`, `admin.html`) — размещение трекера и форм.
* `web/src/tracker/` (или файл `swipies-tracker.js`) — код клиентского трекера.
* `src/attribution/` — аналитический движок, расчет ROAS/CAC, CLI-команды.
* `src/tracker_service.py` — изолированный Flask-сервис приёма событий для порта 5001.
* `migrations/V1.5__add_attribution_utm_columns.sql` — SQL-миграция.
* `config/attribution_config.yaml` — локальный конфиг правил атрибуции.

### 6.2 Deny-List (СТРОГО ЗАПРЕЩЕНО читать, индексировать и логировать)
* 🚫 **`.env` и любые локальные конфигурации с боевыми секретами.**
* 🚫 **Директория `atmos payment system/` и `server/`** — там хранятся боевые ключи эквайринга Atmos, закрытые сертификаты и `RAGFLOW_API_KEY`.
* 🚫 **`docs/specs/` (платёжные спецификации)** — платёжные схемы, внутренняя банковская архитектура и антифрод.
* 🚫 **Любые файлы сертификатов и ключей:** `*.der`, `*.pem`, `*.key`, `*.pfx`.

---

## 7. Политика PII и Data Retention

### 7.1 Политика по IP-адресам
* **Сырой IP-адрес клиента НЕ СОХРАНЯЕТСЯ в базе данных.**
* **Алгоритм обработки в памяти Flask Blueprint:**
  1. Из заголовка `X-Forwarded-For` извлекается IP.
  2. Немедленно в оперативной памяти вычисляется отпечаток:
     $$\text{session\_ip\_hash} = \text{SHA256}(\text{IP} + \text{Daily\_Salt})$$
     (где `Daily_Salt` ротируется каждые 24 часа). Это позволяет считать уникальных посетителей за сутки, но исключает обратное восстановление IP.
  3. По локальной базе GeoIP определяются `country="UZ"` и `city="Tashkent"`.
  4. Сырой IP немедленно удаляется из контекста запроса.

### 7.2 Data Retention Policy (Сроки хранения)
1. **Сырые события (`attribution_raw_events`):**
   * Хранятся ровно **30 календарных дней**.
   * Содержат: `session_id`, `event_time`, `page_path`, `active_time_seconds`, `utm_*`, `ip_hash`.
   * Автоматически удаляются задачей очистки (`DELETE ... WHERE event_time < NOW() - INTERVAL 30 DAY`).
2. **Агрегированная витрина (`daily_attribution_summary`):**
   * Хранится **24 месяца** для построения годовых отчетов.
   * Содержит только агрегированные счетчики: `date`, `utm_source`, `utm_campaign`, `visits`, `unique_sessions`, `avg_active_seconds`, `paid_transactions_count`, `revenue_uzs`.
3. **Соответствие нормам:** Закон Республики Узбекистан «О персональных данных» № ЗРУ-547 и стандарты GDPR.

---

## 8. Границы скоупа (Scope Matrix)

### 8.1 In-Scope (v1 этого трека)
1. Клиентский трекер `swipies-tracker.js` (<3.5 КБ, zero dependencies, активное время, UTM persistence).
2. Изолированный Flask-сервис `src/tracker_service.py` (порт 5001, Gunicorn) с эндпоинтом `POST /api/v1/track/event` и анонимизацией IP.
3. Аддитивная SQL-миграция `payment_transaction` (добавление `session_id`, `utm_*`).
4. Проброс `session_id` из формы оплаты через `/api/pay/apply` в `PaymentTransactionService.create_pending()`.
5. Создание защищенного View `v_attribution_payments` и юзера `analytics_ro`.
6. Модели атрибуции **First-Touch** (по 30-дневной cookie) и **Last-Touch** (по сессии оплаты).
7. Сводный отчет CLI:
   ```bash
   python -m src.cli attribution-report --from 2026-09-01 --to 2026-09-07 --model last-touch
   ```
   Сопоставление: Расходы (из Meta Ads Ledger в USD) $\times$ Курс $\leftrightarrow$ Доходы (из MySQL View в UZS) $\rightarrow$ Расчет реального **ROAS, CAC, CPL**.

### 8.2 Out of Scope (Строго исключено из v1)
* ❌ Real-time live дашборды (WebSockets, графики в реальном времени).
* ❌ ML-модели скоринга вероятности оплаты.
* ❌ Алгоритмическая Multi-Touch атрибуция (векторы Шепли, цепи Маркова).
* ❌ Рекламные каналы, кроме Meta UTM (Google/Yandex подключаются в следующих фазах).
* ❌ Запись экранов сессий (вебвизор/Hotjar).
* ❌ Closed-Loop авто-биддинг в Meta без участия человека.

---

## 9. Проверяемые критерии приёмки (Acceptance Criteria)

| ID | Критерий | Требование и Сценарий проверки (Тестируемость) |
| :--- | :--- | :--- |
| **AC-01** | **Аддитивность миграции БД** | Миграция выполняется на копии боевой схемы `payment_transaction`. Проверка: существующие платежи не затронуты, дефолтные значения `NULL`, время выполнения `< 1 сек`. |
| **AC-02** | **Zero-Impact на платёжное ядро** | Интеграционный тест: создание платежа через `/api/pay/apply` с переданными UTM и без них. В обоих случаях платёж создаётся со статусом `PENDING`, сумма `expected_amount_uzs` не меняется, `GET_LOCK` работает штатно. |
| **AC-03** | **Изоляция прав `analytics_ro`** | Тест прав MySQL: пользователь `analytics_ro` успешно читает `v_attribution_payments`, но при попытке `SELECT gateway_response FROM payment_transaction` получает `ERROR 1142 (42000): SELECT command denied`. Попытки `INSERT/UPDATE` блокируются. |
| **AC-04** | **Анонимизация IP и сокрытие соли** | В коде и БД отсутствует колонка сырого IP. Поле `ip_hash` содержит SHA256 с суточной солью. В файле спецификации и репозитории отсутствует литерал соли (используется плейсхолдер `{{PAYER_HASH_SALT}}`). |
| **AC-05** | **Точность First/Last Touch моделей** | Тест сквозной цепочки: клик с Кампании A в День 1 $\rightarrow$ клик с Кампании B в День 2 $\rightarrow$ оплата. Модель `--model first-touch` относит доход к Кампании A, `--model last-touch` — к Кампании B. |
| **AC-06** | **Retention Purge сырых логов** | Скрипт очистки удаляет записи из `attribution_raw_events` старше 30 дней, не затрагивая витрину `daily_attribution_summary`. |
| **AC-07** | **Безопасность кодовой базы (Allow-List)** | Автоматический линтер проверяет отсутствие обращений из трекингового модуля к `atmos payment system/`, `.env` и `docs/specs/`. |

---

## 10. ГЕЙТ 1: Подтверждение спецификации

Все замечания устранены:
1. **Колонки и статусы View приведены в 100% соответствие реальной DDL-схеме:** Учтены реальные поля (`paid_amount_uzs`, `account_email`, `create_date`, строго валюта `UZS`). Фильтр статуса строго `WHERE pt.status = 'PAID'`.
2. **Литерал соли удален:** Заменён на плейсхолдер `{{PAYER_HASH_SALT}}`.
3. **Физическая изоляция процессов (Blast Radius):** Трекинг запускается как отдельный сервис на Flask (`src/tracker_service.py`) под Gunicorn на порту 5001 (`swipies-tracker.service`), полностью изолированный по памяти, GIL и пулу воркеров от платежного ядра на порту 5000 (`swipies-api.service`).
4. **Прямое безопасное подключение к БД:** Пользователь `analytics_ro` на `127.0.0.1` с лимитом `max_execution_time=3000` и чтением строго через View.
