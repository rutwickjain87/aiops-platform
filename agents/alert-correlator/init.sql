-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Alerts table: stores raw alert + Voyage AI embedding
CREATE TABLE IF NOT EXISTS alerts (
    id          SERIAL PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,          -- AlertManager fingerprint hash
    name        TEXT NOT NULL,                 -- alertname label
    severity    TEXT NOT NULL DEFAULT 'warning',
    labels      JSONB NOT NULL DEFAULT '{}',
    annotations JSONB NOT NULL DEFAULT '{}',
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    embedding   vector(1024),                  -- voyage-3-lite: 1024 dims
    status      TEXT NOT NULL DEFAULT 'firing' -- firing | resolved
);

-- Incidents table: groups of correlated alerts
CREATE TABLE IF NOT EXISTS incidents (
    id          SERIAL PRIMARY KEY,
    incident_id TEXT NOT NULL UNIQUE,          -- e.g. INC-20260518-001
    title       TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'warning',
    alert_ids   INTEGER[] NOT NULL,
    root_cause  TEXT,
    summary     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status      TEXT NOT NULL DEFAULT 'open'   -- open | resolved
);

-- Index for fast cosine similarity search (ivfflat)
-- lists=100 is a good default for <1M rows
CREATE INDEX IF NOT EXISTS alerts_embedding_cosine_idx
    ON alerts USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index for time-bounded queries
CREATE INDEX IF NOT EXISTS alerts_received_at_idx ON alerts (received_at DESC);
CREATE INDEX IF NOT EXISTS alerts_status_idx ON alerts (status);
