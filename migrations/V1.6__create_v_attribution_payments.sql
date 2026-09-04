-- ==============================================================================
-- SWIPIES Analytics & Attribution — Secure Read-Only View
-- Migration: V1.6__create_v_attribution_payments.sql
-- Target: MySQL 8.0+ (swipies_db)
-- Security: PII Masking, No Gateway Raw Responses, Strict PAID Filter
-- ==============================================================================

-- 1. Создание безопасного представления для аналитики
-- Исключены: gateway_response, account_email (сырой), card_pan, card_token, audit_note
-- Фильтр: строго pt.status = 'PAID' (только подтверждённые успешные конверсии)

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
    -- Псевдоанонимизированный идентификатор плательщика для подсчёта LTV и повторных оплат.
    -- Соль {{PAYER_HASH_SALT}} подставляется деплой-скриптом из переменной окружения ATTRIBUTION_SALT.
    SHA2(CONCAT(pt.account_email, '{{PAYER_HASH_SALT}}'), 256) AS masked_payer_hash
FROM swipies_db.payment_transaction pt
WHERE pt.status = 'PAID';

-- 2. Создание изолированного пользователя и выдача прав
-- ВНИМАНИЕ: Пароль STRONG_RANDOM_RO_PASSWORD заменяется при деплое.
-- CREATE USER IF NOT EXISTS 'analytics_ro'@'127.0.0.1' IDENTIFIED BY 'STRONG_RANDOM_RO_PASSWORD';
-- REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'analytics_ro'@'127.0.0.1';
-- GRANT SELECT ON swipies_db.v_attribution_payments TO 'analytics_ro'@'127.0.0.1';
-- FLUSH PRIVILEGES;
