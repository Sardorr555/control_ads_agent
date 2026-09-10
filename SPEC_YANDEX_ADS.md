# SWIPIES Yandex Direct (РСЯ & Поиск) Automation — Specification (Track 7)

**Version:** 1.0.0  
**Project:** Yandex Direct API v5 B2B Ads Automation & Local UZS Accounting  
**Track:** Track 7 (Yandex Direct Management & CIS Enterprise Inbound)  
**Status:** IMPLEMENTED WITH DRY-RUN & SAFETY GATES  

---

## 1. Executive Summary & WHY (Бизнес-цели и локальный биллинг)

Яндекс Директ — ключевой канал для enterprise-клиентов и официальной бухгалтерии в Узбекистане:
1. **Прямой локальный договор и биллинг в UZS**:
   * Оплата с корпоративного расчетного счета узбекского банка без валютной конвертации.
   * Официальные электронные счета-фактуры (ЭСФ) через Didox / Soliq.uz с НДС 12%.
2. **Фокус на РСЯ (Рекламная Сеть Яндекса)**:
   * Размещение графических и текстово-графических блоков на ведущих деловых порталах (*Spot.uz, Gazeta.uz, Kun.uz, Daryo.uz, RBK*).
   * Охват руководителей компаний во время чтения утренних бизнес-новостей.

---

## 2. Архитектура безопасности: Financial Zero-Trust

1. **Режим суточного бюджета `STANDARD` (Zero Overspend)**:
   * В режиме `STANDARD` показы кампании мгновенно останавливаются при исчерпании дневного лимита. Никаких скрытых 200% списаний.
2. **Создание строго в состоянии `SUSPENDED` / `OFF`**:
   * Все кампании и группы объявлений создаются остановленными.
3. **Бесшовная разметка UTM (Track 3 Integration)**:
   * Автоматическая подстановка UTM-меток:
     `{href}?utm_source=yandex&utm_medium=cpc&utm_campaign={campaign_name}&utm_content={adgroup_id}&utm_term={keyword}&yclid={yclid}`
   * Наш трекер `swipies-tracker.js` перехватывает клик и `yclid`, связывая их с оплатами в сумах (UZS).
4. **Режим Dry-Run / Sandbox**:
   * Поддержка песочницы (`api-sandbox.direct.yandex.com`) и автономного режима симуляции.
