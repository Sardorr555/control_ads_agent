-- ==============================================================================
-- SWIPIES Traffic Attribution & Analytics Engine (Track 3)
-- Migration: V1.7__create_attribution_events.sql
-- Target: SQLite 3.37+ (WAL Mode enabled)
-- Tables: attribution_raw_events (30d retention), daily_attribution_summary (365d)
-- ==============================================================================

-- 1. Таблица сырых событий посещений и вовлечённости
CREATE TABLE IF NOT EXISTS attribution_raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id VARCHAR(64) NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    page_path VARCHAR(255) NOT NULL,
    time_on_page_sec INTEGER NOT NULL DEFAULT 0,
    utm_source VARCHAR(64) NULL,
    utm_medium VARCHAR(64) NULL,
    utm_campaign VARCHAR(128) NULL,
    utm_content VARCHAR(128) NULL,
    utm_term VARCHAR(128) NULL,
    referrer VARCHAR(512) NULL,
    ip_hash VARCHAR(64) NOT NULL,
    country VARCHAR(2) NULL,
    city VARCHAR(64) NULL,
    user_agent VARCHAR(255) NULL,
    event_type VARCHAR(32) NOT NULL DEFAULT 'pageview'
);

-- Индексы для быстрого поиска и агрегации
CREATE INDEX IF NOT EXISTS idx_are_session_time ON attribution_raw_events (session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_are_campaign ON attribution_raw_events (utm_campaign);
CREATE INDEX IF NOT EXISTS idx_are_ip_time ON attribution_raw_events (ip_hash, timestamp);
CREATE INDEX IF NOT EXISTS idx_are_timestamp ON attribution_raw_events (timestamp);

-- 2. Таблица агрегированных ежедневных метрик (retention 365 дней)
CREATE TABLE IF NOT EXISTS daily_attribution_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_date DATE NOT NULL,
    utm_source VARCHAR(64) NOT NULL DEFAULT '(none)',
    utm_medium VARCHAR(64) NOT NULL DEFAULT '(none)',
    utm_campaign VARCHAR(128) NOT NULL DEFAULT '(direct)',
    visits_count INTEGER NOT NULL DEFAULT 0,
    unique_sessions INTEGER NOT NULL DEFAULT 0,
    conversions_count INTEGER NOT NULL DEFAULT 0,
    revenue_uzs INTEGER NOT NULL DEFAULT 0,
    avg_duration_sec REAL NOT NULL DEFAULT 0.0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(summary_date, utm_source, utm_medium, utm_campaign)
);

CREATE INDEX IF NOT EXISTS idx_das_date_campaign ON daily_attribution_summary (summary_date, utm_campaign);
