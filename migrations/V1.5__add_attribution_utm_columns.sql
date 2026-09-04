-- ==============================================================================
-- SWIPIES Payment Engine — Additive Schema Migration
-- Migration: V1.5__add_attribution_utm_columns.sql
-- Target: MySQL 8.0+ (swipies_db.payment_transaction)
-- Safety: 100% ADDITIVE, NON-LOCKING, STRICTLY NULLABLE
-- ==============================================================================

-- 1. Добавление колонок сессии и UTM-атрибуции
-- Все новые поля строго NULLABLE со значением по умолчанию NULL.
-- Существующие строки и логика биллинга не затрагиваются.

ALTER TABLE payment_transaction
    ADD COLUMN session_id VARCHAR(64) NULL AFTER status,
    ADD COLUMN utm_source VARCHAR(64) NULL AFTER session_id,
    ADD COLUMN utm_medium VARCHAR(64) NULL AFTER utm_source,
    ADD COLUMN utm_campaign VARCHAR(128) NULL AFTER utm_medium,
    ADD COLUMN utm_content VARCHAR(128) NULL AFTER utm_campaign,
    ADD COLUMN utm_term VARCHAR(128) NULL AFTER utm_content,
    ADD INDEX idx_pt_session_id (session_id),
    ADD INDEX idx_pt_utm_campaign (utm_campaign);

-- Verification Query:
-- SELECT id, transaction_id, status, session_id, utm_source, utm_campaign 
-- FROM payment_transaction LIMIT 5;
