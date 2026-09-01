PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS demo_users (
  user_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('Executive','Analyst','Operator','Data Steward')),
  password_salt TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  csrf_hash TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES demo_users(user_id),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  run_id TEXT PRIMARY KEY,
  dataset_name TEXT NOT NULL,
  source_name TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  contract_version INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('accepted','rejected','unchanged')),
  loaded_at TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  trusted_row_count INTEGER NOT NULL DEFAULT 0,
  issue_row_count INTEGER NOT NULL DEFAULT 0,
  duplicate_row_count INTEGER NOT NULL DEFAULT 0,
  quality_score REAL NOT NULL DEFAULT 0,
  unexpected_columns_json TEXT NOT NULL DEFAULT '[]',
  missing_columns_json TEXT NOT NULL DEFAULT '[]',
  source_max_updated_at TEXT,
  notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ingestion_hash ON ingestion_runs(content_sha256, status);
CREATE INDEX IF NOT EXISTS idx_ingestion_loaded ON ingestion_runs(loaded_at DESC);

CREATE TABLE IF NOT EXISTS ingestion_issues (
  issue_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES ingestion_runs(run_id) ON DELETE CASCADE,
  row_number INTEGER NOT NULL,
  request_id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  value_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_requests (
  run_id TEXT NOT NULL REFERENCES ingestion_runs(run_id) ON DELETE CASCADE,
  row_number INTEGER NOT NULL,
  request_id TEXT NOT NULL,
  created_at TEXT,
  closed_at TEXT,
  status TEXT NOT NULL,
  priority TEXT NOT NULL,
  category TEXT NOT NULL,
  subcategory TEXT NOT NULL,
  location TEXT NOT NULL,
  team TEXT NOT NULL,
  owner TEXT NOT NULL,
  channel TEXT NOT NULL,
  sla_hours REAL,
  resolution_hours REAL,
  reopened INTEGER NOT NULL DEFAULT 0,
  satisfaction_score REAL,
  last_updated_at TEXT,
  source_system TEXT NOT NULL,
  trusted INTEGER NOT NULL CHECK(trusted IN (0,1)),
  raw_json TEXT NOT NULL,
  PRIMARY KEY(run_id, row_number)
);
CREATE INDEX IF NOT EXISTS idx_service_requests_run_trusted ON service_requests(run_id, trusted);
CREATE INDEX IF NOT EXISTS idx_service_requests_request ON service_requests(request_id);

CREATE TABLE IF NOT EXISTS workflow_cases (
  case_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  owner TEXT NOT NULL,
  created_at TEXT NOT NULL,
  due_at TEXT NOT NULL,
  source TEXT NOT NULL,
  expected_impact TEXT NOT NULL,
  baseline_metric TEXT NOT NULL,
  baseline_value REAL NOT NULL,
  target_value REAL NOT NULL,
  current_value REAL NOT NULL,
  unit TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  audit_id TEXT PRIMARY KEY,
  event_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  actor_role TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_event_at ON audit_events(event_at DESC);

CREATE TABLE IF NOT EXISTS action_outcomes (
  outcome_id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES workflow_cases(case_id) ON DELETE CASCADE,
  metric TEXT NOT NULL,
  baseline_value REAL NOT NULL,
  measured_value REAL NOT NULL,
  target_value REAL NOT NULL,
  unit TEXT NOT NULL,
  measured_at TEXT NOT NULL,
  result TEXT NOT NULL CHECK(result IN ('Improved','Mixed','Insufficient data')),
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS refresh_schedule (
  schedule_id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  interval_minutes INTEGER NOT NULL,
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
  last_checked_at TEXT,
  last_result TEXT,
  next_due_at TEXT NOT NULL
);
