# SWIPIES Meta (Instagram / Facebook) Ads Automation — Specification (Track 6)

**Version:** 1.0.0  
**Project:** Meta Marketing API B2B Lead Generation & Inbound Pipeline  
**Track:** Track 6 (Meta / Instagram Ads Management)  
**Status:** IMPLEMENTED WITH DRY-RUN & SAFETY GATES  

---

## 1. Executive Summary & WHY (Бизнес-цели и специфика Meta в ЦА)

В Узбекистане и Центральной Азии **Instagram является главной бизнес-витриной**:
* Владельцы бизнеса, руководители банков, IT-директора и топ-менеджеры ежедневно проводят в Instagram от 1 до 2 часов.
* Таргетинг на аудитории с интересами *«Банковское дело, Искусственный интеллект, SaaS, Высший менеджмент»* в Ташкенте и Казахстане даёт ключевой поток входящих лидов.
* Цель модуля — автоматизировать создание кампаний для продвижения SWIPIES с генерацией лидов и переходов на лендинг.

---

## 2. Архитектура безопасности: Financial Zero-Trust

1. **Создание строго на паузе (`status: PAUSED`)**:
   * Ни одна кампания (`Campaign`), группа (`AdSet`) или объявление (`Ad`) не создаются в активном статусе.
2. **Account Spend Caps & Daily Budget**:
   * Бюджеты задаются в центах/микро-долларах (например, $15/день = 1,500 центов).
   * Максимальный допустимый лимит безопасности — $500/сутки.
3. **Бесшовная разметка UTM (Track 3 Integration)**:
   * Каждое объявление автоматически получает `url_tags`:
     `utm_source=meta&utm_medium=cpc&utm_campaign={_campaign}&utm_content={_adset}&fbclid={fbclid}`
   * Наш трекер `swipies-tracker.js` перехватывает клик и `fbclid`, связывая их с оплатами в сумах (UZS).
4. **Режим Dry-Run / Zero-Key**:
   * Без ключей API система производит полную симуляцию валидации и генерацию ресурсов (`act_...`, `camp_...`, `adset_...`, `ad_...`).
