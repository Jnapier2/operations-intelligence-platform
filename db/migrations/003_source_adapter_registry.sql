PRAGMA foreign_keys = ON;

ALTER TABLE refresh_schedule ADD COLUMN connector_id TEXT NOT NULL DEFAULT 'demo-local';
