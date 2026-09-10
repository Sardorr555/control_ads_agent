# SWIPIES Twitter / X Ads Automation — Functional Specification (Track 5)

**Version:** 1.0.0  
**Project:** Twitter / X Ads B2B Tech Lead Generation & Zero-Trust Automation  
**Track:** Track 5 (Twitter / X Ads Management & Global Inbound)  
**Status:** IMPLEMENTED WITH DRY-RUN & SAFETY GATES  

---

## 1. Executive Summary & WHY (Бизнес-цели и специфика X/Twitter)

X (бывший Twitter) является глобальной платформой №1 для IT-фаундеров, AI-исследователей, CTO, технических директоров и инженеров.
Для платформы **SWIPIES (Enterprise RAG & Local AI Platform)** реклама в X даёт:
1. **Прямой выход на технических ЛПР (CTO, VP of AI, Head of Data)**: Таргетинг по подписчикам профильных AI-аккаунтов (`@OpenAI`, `@AnthropicAI`, `@LangChainAI`, `@huggingface`).
2. **Низкий CPM/CPC в B2B**: Переходы по техническим кейсам в ленте обходятся дешевле, чем контекст в Google Search, при гораздо большем объёме охвата.
3. **Бесшовная сквозная аналитика (Track 3 Integration)**:
   * Автоматическая подстановка UTM-меток:
     `{website_url}?utm_source=twitter&utm_medium=cpc&utm_campaign={_campaign}&utm_content={_line_item}&twclid={twclid}`
   * Наш трекер `swipies-tracker.js` и движок атрибуции `src.cli attribution-report` связывают клики из X с регистрациями и оплатами.

---

## 2. Архитектура безопасности: Financial Zero-Trust

1. **Создание строго на паузе (`entity_status: PAUSED`)**:
   * Ни одна кампания или группа объявлений (Line Item) не создаётся в активном режиме без явного подтверждения человека.
2. **Лимиты бюджетов (Spend Caps)**:
   * Бюджет задается в микро-валюте (`daily_budget_amount_local_micro`, 1,000,000 micros = $1.00).
   * Максимальный допустимый суточный лимит по умолчанию: $500.
3. **Dry-Run / Zero-Key симуляция**:
   * Без ключей API система производит полную симуляцию валидации и генерацию ресурсов X Ads (`camp_...`, `line_...`, `prom_...`).
