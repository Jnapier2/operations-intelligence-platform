PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS automation_rules (
  rule_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
  severity TEXT NOT NULL,
  owner_role TEXT NOT NULL,
  cooldown_minutes INTEGER NOT NULL,
  dedupe_key TEXT NOT NULL,
  conditions_json TEXT NOT NULL,
  action_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_executions (
  execution_id TEXT PRIMARY KEY,
  rule_id TEXT NOT NULL REFERENCES automation_rules(rule_id),
  evaluated_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('Triggered','Suppressed','No Match','Simulated')),
  fingerprint_sha256 TEXT NOT NULL,
  reason TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  case_id TEXT,
  UNIQUE(rule_id, fingerprint_sha256, status)
);
CREATE INDEX IF NOT EXISTS idx_automation_execution_rule_time ON automation_executions(rule_id, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS problem_records (
  problem_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  owner TEXT NOT NULL,
  hypothesis TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS improvement_initiatives (
  initiative_id TEXT PRIMARY KEY,
  problem_id TEXT REFERENCES problem_records(problem_id),
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  owner TEXT NOT NULL,
  baseline_metric TEXT NOT NULL,
  baseline_value REAL NOT NULL,
  target_value REAL NOT NULL,
  measured_value REAL NOT NULL,
  unit TEXT NOT NULL,
  hours_saved_monthly REAL NOT NULL DEFAULT 0,
  backlog_avoided INTEGER NOT NULL DEFAULT 0,
  sla_improvement_points REAL NOT NULL DEFAULT 0,
  confidence_pct REAL NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS playbooks (
  playbook_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  steps_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playbook_runs (
  run_id TEXT PRIMARY KEY,
  playbook_id TEXT NOT NULL REFERENCES playbooks(playbook_id),
  case_id TEXT,
  status TEXT NOT NULL CHECK(status IN ('Active','Completed','Canceled')),
  current_step INTEGER NOT NULL DEFAULT 0,
  steps_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_playbook_run_updated ON playbook_runs(updated_at DESC);
