# SWIPIES Google Ads Search Automation — Functional Specification (Track 4)

**Version:** 1.0.0  
**Project:** Google Ads Search Automation, Keyword Pipeline & Financial Zero-Trust  
**Track:** Track 4 (Google Ads Management & Search Inbound)  
**Status:** IMPLEMENTED WITH DRY-RUN & SAFETY GATES  

---

## 1. Executive Summary & WHY (Бизнес-цели и безопасность)

Рекламный агент для Google Ads автоматизирует создание и оптимизацию поисковых кампаний для SWIPIES (Enterprise RAG & AI Platform) на рынках Узбекистана, Казахстана и глобального поиска.

### Главный архитектурный принцип: Financial Zero-Trust & Pre-Flight Validation
1. **Кампании создаются строго на паузе (`status: PAUSED`)**: Ни одна кампания или группа объявлений не может активироваться автоматически без явного флага подтверждения человека (`--confirm-budget-approval`).
2. **Защита от Google Ads 200% Pacing Rule (Overdelivery Guard)**:
   * Google Ads имеет официальное правило: в дни с повышенным спросом платформа может списать **до 200% суточного бюджета**.
   * Защитный механизм агента: автоматическая проверка суточного лимита. Если дневной бюджет превышает $50, агент требует подтверждение с учетом максимального суточного расхода (2x).
3. **Нативный сухой прогон (Native Dry-Run)**:
   * В режиме без ключей или с флагом `--dry-run` система производит глубокую симуляцию валидации Google Ads API (политики длины заголовков, описаний, запрет восклицательных знаков в заголовках, структура групп и минус-слов) без единого сетевого списания.
4. **Бесшовная сквозная связка с трекером (Track 3 Integration)**:
   * Каждое объявление автоматически получает `tracking_url_template`:
     `{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign={_campaign}&utm_content={_adgroup}&utm_term={keyword}&gclid={gclid}`
   * Наш трекер (`swipies-tracker.js`) на сайте SWIPIES автоматически регистрирует этот переход, сохраняет сессию и связывает её с последующей оплатой тарифа через Atmos в сумах (UZS).

---

## 2. Спецификация структур данных (Data Contracts)

### 2.1 Кампания (`GoogleCampaignDTO`)
* `name`: Название кампании (например, `SWIPIES_B2B_AI_RAG_UZ_CIS`).
* `daily_budget_micros`: Суточный бюджет в микро-валюте ($1 = 1,000,000 micros). Минимальный порог: 1,000,000 micros ($1), максимальный порог безопасности: 500,000,000 micros ($500).
* `status`: Статус кампании (`PAUSED` по умолчанию, строго проверяется валидатором).
* `bidding_strategy`: `MANUAL_CPC`, `MAXIMIZE_CLICKS` или `TARGET_CPA`.
* `target_locations`: Список целевых гео-локаций (`Uzbekistan`, `Kazakhstan`).
* `target_languages`: Языки показа (`ru`, `en`, `uz`).
* `ad_groups`: Список групп объявлений.

### 2.2 Группа объявлений (`GoogleAdGroupDTO`)
* `name`: Название группы (например, `Enterprise_RAG_Search`).
* `cpc_bid_micros`: Базовая ставка за клик (default: 500,000 micros = $0.50).
* `keywords`: Список ключевых слов с типами соответствия.
* `ads`: Список адаптивных поисковых объявлений (RSA).

### 2.3 Ключевые слова (`GoogleKeywordDTO`)
* `text`: Ключевая фраза (без мусора и спецсимволов).
* `match_type`:
  * `EXACT`: точное соответствие (`[enterprise rag]`)
  * `PHRASE`: фразовое соответствие (`"ии для банков"`)
  * `BROAD`: широкое соответствие
* `is_negative`: Флаг минус-слова (исключение нецелевого трафика: *бесплатно, вакансии, торрент*).

### 2.4 Адаптивные поисковые объявления RSA (`GoogleResponsiveSearchAdDTO`)
* `headlines`: Заголовки (минимум 3, максимум 15, длина каждого $\le 30$ символов).
* `descriptions`: Описания (минимум 2, максимум 4, длина каждого $\le 90$ символов).
* `final_urls`: Целевые посадочные страницы (валидные HTTP/HTTPS URL).
* `path1` / `path2`: Отображаемые пути в URL (до 15 символов каждый).
* `tracking_url_template`: Шаблон сквозной аналитики с подстановкой `{lpurl}` и UTM-меток.

---

## 3. Режимы работы Google Ads Client

1. **Dry-Run / Zero-Key Mode**:
   * Полная проверка всех ограничений Google Ads Policy локально.
   * Формирование виртуальных resource names (`customers/{id}/campaigns/{id}`).
   * Расчет бюджетов и метрик без необходимости иметь боевые токены.
2. **Live API Mode (при наличии токенов в среде)**:
   * Переменные окружения: `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_CUSTOMER_ID`.
   * Серверная валидация Google через `validate_only=True` до ручного подтверждения.
