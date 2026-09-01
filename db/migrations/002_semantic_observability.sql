PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS kpi_definitions (
  kpi_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  owner TEXT NOT NULL,
  current_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kpi_versions (
  kpi_id TEXT NOT NULL REFERENCES kpi_definitions(kpi_id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  definition TEXT NOT NULL,
  formula TEXT NOT NULL,
  grain TEXT NOT NULL,
  window_text TEXT NOT NULL,
  target TEXT NOT NULL,
  source_fields_json TEXT NOT NULL,
  limitations TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(kpi_id, version)
);

CREATE TABLE IF NOT EXISTS forecast_backtests (
  backtest_id TEXT PRIMARY KEY,
  signature_sha256 TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  dataset_run_id TEXT,
  horizon_days INTEGER NOT NULL,
  mean_absolute_error REAL NOT NULL,
  mean_bias REAL NOT NULL,
  observed_daily_flow REAL NOT NULL,
  model_version TEXT NOT NULL,
  details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_feedback (
  feedback_id TEXT PRIMARY KEY,
  alert_key TEXT NOT NULL,
  reviewed_at TEXT NOT NULL,
  reviewer_role TEXT NOT NULL,
  confirmed_signal INTEGER NOT NULL CHECK(confirmed_signal IN (0,1)),
  useful INTEGER NOT NULL CHECK(useful IN (0,1)),
  notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_alert_feedback_reviewed ON alert_feedback(reviewed_at DESC);
