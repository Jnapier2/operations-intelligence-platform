#!/usr/bin/env python3
"""Governed project-local SQLite state for the portfolio enterprise demo.

No network activity is performed. Migrations are append-only and project-local.
The database lives under state/ and is intentionally excluded from release ZIPs.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from source_connectors import read_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "state" / "operations_intelligence.db"
CONTRACT = ROOT / "config" / "data_contract.json"
KPI_CATALOG = ROOT / "config" / "kpi_catalog.json"
SLO_CATALOG = ROOT / "config" / "slo_catalog.json"
AUTOMATION_CATALOG = ROOT / "config" / "automation_catalog.json"
PLAYBOOK_CATALOG = ROOT / "config" / "playbook_catalog.json"
IMPROVEMENT_CATALOG = ROOT / "config" / "improvement_catalog.json"
MIGRATIONS = ROOT / "db" / "migrations"
DEMO_CSV = ROOT / "public" / "data" / "service_requests_demo.csv"
UTC = timezone.utc

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "Executive": {"read_cases", "manage_cases", "read_audit", "read_governance", "read_observability", "ingest_data", "record_outcomes", "record_backtests", "read_automation", "run_automation", "read_improvements", "manage_playbooks"},
    "Analyst": {"read_cases", "manage_cases", "read_audit", "read_governance", "read_observability", "ingest_data", "record_outcomes", "record_backtests", "read_automation", "run_automation", "read_improvements", "manage_playbooks"},
    "Operator": {"read_cases", "manage_cases", "record_outcomes", "read_automation", "read_improvements", "manage_playbooks"},
    "Data Steward": {"read_cases", "read_audit", "read_governance", "read_observability", "ingest_data", "manage_kpis", "read_automation", "run_automation", "read_improvements", "manage_playbooks"},
}

SEVERITY_WEIGHT = {"Critical": 4.0, "High": 2.5, "Medium": 1.5, "Low": 0.75}
DEMO_PASSWORD = "portfolio-demo"
PASSWORD_ITERATIONS = 210_000


def password_hash(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS).hex()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    try:
        actual = password_hash(password, salt_hex)
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(actual, expected_hash)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_dt(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def as_float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text)
        return parsed if math.isfinite(parsed) else None
    except ValueError:
        return None


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def bool_value(value: str | None) -> bool:
    return (value or "").strip().lower() in {"yes", "true", "1", "y"}


@dataclass(frozen=True)
class Session:
    user_id: str
    display_name: str
    role: str
    csrf_token: str
    token: str
    expires_at: str


class ManagedConnection(sqlite3.Connection):
    """Commit or roll back, then release the database handle on context exit."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class OperationalStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.kpi_catalog = json.loads(KPI_CATALOG.read_text(encoding="utf-8"))
        self.slo_catalog = json.loads(SLO_CATALOG.read_text(encoding="utf-8"))
        self.automation_catalog = json.loads(AUTOMATION_CATALOG.read_text(encoding="utf-8"))
        self.playbook_catalog = json.loads(PLAYBOOK_CATALOG.read_text(encoding="utf-8"))
        self.improvement_catalog = json.loads(IMPROVEMENT_CATALOG.read_text(encoding="utf-8"))
        self.apply_migrations()
        self.seed_reference_data()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0, factory=ManagedConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def apply_migrations(self) -> list[int]:
        applied: list[int] = []
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
            known = {int(row[0]) for row in conn.execute("SELECT version FROM schema_migrations")}
            for path in sorted(MIGRATIONS.glob("*.sql")):
                prefix = path.name.split("_", 1)[0]
                if not prefix.isdigit():
                    raise RuntimeError(f"Migration name must begin with an integer: {path.name}")
                version = int(prefix)
                if version in known:
                    continue
                script = path.read_text(encoding="utf-8")
                conn.executescript(script)
                conn.execute(
                    "INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,?)",
                    (version, path.name, now_iso()),
                )
                applied.append(version)
        return applied

    def seed_reference_data(self) -> None:
        users = [
            ("exec-demo", "Executive Demo", "Executive"),
            ("analyst-demo", "Analyst Demo", "Analyst"),
            ("operator-demo", "Operator Demo", "Operator"),
            ("steward-demo", "Data Steward Demo", "Data Steward"),
        ]
        with self.connect() as conn:
            for user_id, display_name, role in users:
                existing = conn.execute("SELECT user_id FROM demo_users WHERE user_id=?", (user_id,)).fetchone()
                if existing is None:
                    salt = secrets.token_hex(16)
                    conn.execute(
                        "INSERT INTO demo_users(user_id,display_name,role,password_salt,password_hash,enabled) VALUES(?,?,?,?,?,1)",
                        (user_id, display_name, role, salt, password_hash(DEMO_PASSWORD, salt)),
                    )
            for item in self.kpi_catalog.get("kpis", []):
                conn.execute(
                    "INSERT OR IGNORE INTO kpi_definitions(kpi_id,name,owner,current_version) VALUES(?,?,?,?)",
                    (item["id"], item["name"], item["owner"], item["version"]),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO kpi_versions(
                    kpi_id,version,effective_date,definition,formula,grain,window_text,target,source_fields_json,limitations,created_by,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item["id"], item["version"], self.kpi_catalog.get("effective_date", "2026-08-29"), item["definition"],
                        item["formula"], item["grain"], item["window"], item["target"], json.dumps(item["source_fields"]),
                        item["limitations"], "release-seed", now_iso(),
                    ),
                )
            existing_cases = conn.execute("SELECT COUNT(*) FROM workflow_cases").fetchone()[0]
            if not existing_cases:
                seeded = [
                    ("CASE-001", "Stabilize Billing & Payments backlog", "Prioritize aged Billing & Payments work and verify daily closure capacity.", "High", "Open", "Operations Manager", 72.0, 88.0, 78.0, "%"),
                    ("CASE-002", "Recover South Service Center SLA", "Review the oldest missed requests, routing, staffing coverage, and exception reasons.", "High", "In Progress", "Service Delivery Lead", 56.1, 85.0, 68.0, "%"),
                    ("CASE-003", "Repair controlled taxonomy exceptions", "Resolve quarantined category and validity defects before publishing final totals.", "High", "Open", "Data Steward", 97.6, 99.0, 97.6, "%"),
                    ("CASE-004", "Measure Account Access knowledge workflow", "Track reopen rate after the documented workflow intervention.", "Medium", "Monitoring", "Operations Analyst", 12.5, 8.0, 7.2, "%"),
                    ("CASE-005", "Close validated workflow improvement", "Confirm resolution-time improvement and preserve measured evidence.", "Medium", "Resolved", "Operations Manager", 31.0, 26.0, 24.4, " hrs"),
                ]
                for idx, row in enumerate(seeded):
                    created = datetime(2026, 8, 24, 18, 0, tzinfo=UTC) - timedelta(days=max(1, 7 - idx))
                    due = datetime(2026, 8, 24, 18, 0, tzinfo=UTC) + timedelta(days=idx + 3)
                    conn.execute(
                        """INSERT INTO workflow_cases(case_id,title,description,priority,status,owner,created_at,due_at,source,expected_impact,baseline_metric,baseline_value,target_value,current_value,unit,notes,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row[0], row[1], row[2], row[3], row[4], row[5], created.isoformat(), due.isoformat(), "Seeded analytical recommendation",
                         "Restore service performance and create measurable follow-up.", "Operational target", row[6], row[7], row[8], row[9], "", now_iso()),
                    )
                conn.executemany(
                    "INSERT INTO audit_events(audit_id,event_at,actor,actor_role,action,entity_type,entity_id,details) VALUES(?,?,?,?,?,?,?,?)",
                    [
                        ("AUD-001", "2026-08-24T18:05:00+00:00", "System", "System", "Dataset validated", "Dataset", "Synthetic Service Operations Demo", "Validation rules executed; blocking rows quarantined from trusted KPI calculations."),
                        ("AUD-002", "2026-08-24T18:06:00+00:00", "System", "System", "Alerts generated", "Analysis", "Current reporting cycle", "Volume, backlog, service-level, and data-quality signals compared with prior baselines."),
                        ("AUD-003", "2026-08-24T18:08:00+00:00", "Operations Manager", "Executive", "Case assigned", "Case", "CASE-002", "Billing recovery case assigned for seven-day follow-up."),
                    ],
                )
                conn.executemany(
                    "INSERT INTO action_outcomes(outcome_id,case_id,metric,baseline_value,measured_value,target_value,unit,measured_at,result,notes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    [
                        ("OUT-001", "CASE-004", "Reopen rate", 12.5, 7.2, 8.0, "%", "2026-08-24T18:00:00+00:00", "Improved", "Comparable 30-day before/after window."),
                        ("OUT-002", "CASE-005", "Median resolution time", 31.0, 24.4, 26.0, " hrs", "2026-08-24T18:00:00+00:00", "Improved", "Comparable 30-day before/after window."),
                    ],
                )
            conn.executemany(
                "INSERT OR IGNORE INTO alert_feedback(feedback_id,alert_key,reviewed_at,reviewer_role,confirmed_signal,useful,notes) VALUES(?,?,?,?,?,?,?)",
                [
                    ("ALERT-FB-001", "billing-backlog", "2026-08-24T18:10:00+00:00", "Analyst", 1, 1, "Synthetic review: confirmed by backlog and SLA evidence."),
                    ("ALERT-FB-002", "south-sla", "2026-08-24T18:12:00+00:00", "Executive", 1, 1, "Synthetic review: location contribution warranted action."),
                    ("ALERT-FB-003", "taxonomy-quality", "2026-08-24T18:14:00+00:00", "Data Steward", 1, 1, "Synthetic review: quarantined defects required stewardship."),
                    ("ALERT-FB-004", "volume-watch", "2026-08-24T18:16:00+00:00", "Analyst", 0, 0, "Synthetic review: movement was explainable and did not warrant escalation."),
                ],
            )
            if conn.execute("SELECT COUNT(*) FROM refresh_schedule").fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO refresh_schedule(schedule_id,source_name,interval_minutes,enabled,last_checked_at,last_result,next_due_at) VALUES(?,?,?,?,?,?,?)",
                    ("demo-local", "Canonical synthetic demo CSV", int(self.contract["freshness"]["ingestion_slo_minutes"]), 1, None, None, now_iso()),
                )
            for rule in self.automation_catalog.get("rules", []):
                conn.execute(
                    """INSERT INTO automation_rules(rule_id,name,description,enabled,severity,owner_role,cooldown_minutes,dedupe_key,conditions_json,action_json,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(rule_id) DO UPDATE SET name=excluded.name,description=excluded.description,severity=excluded.severity,owner_role=excluded.owner_role,cooldown_minutes=excluded.cooldown_minutes,dedupe_key=excluded.dedupe_key,conditions_json=excluded.conditions_json,action_json=excluded.action_json,updated_at=excluded.updated_at""",
                    (rule["id"], rule["name"], rule["description"], 1 if rule.get("enabled", True) else 0, rule["severity"], rule["owner_role"], int(rule["cooldown_minutes"]), rule["dedupe_key"], json.dumps(rule["conditions"], separators=(",", ":")), json.dumps(rule["action"], separators=(",", ":")), now_iso()),
                )
            for playbook in self.playbook_catalog.get("playbooks", []):
                conn.execute(
                    """INSERT INTO playbooks(playbook_id,name,description,steps_json,updated_at) VALUES(?,?,?,?,?)
                    ON CONFLICT(playbook_id) DO UPDATE SET name=excluded.name,description=excluded.description,steps_json=excluded.steps_json,updated_at=excluded.updated_at""",
                    (playbook["id"], playbook["name"], playbook["description"], json.dumps(playbook["steps"], separators=(",", ":")), now_iso()),
                )
            if conn.execute("SELECT COUNT(*) FROM problem_records").fetchone()[0] == 0:
                for item in self.improvement_catalog.get("problems", []):
                    conn.execute(
                        "INSERT INTO problem_records(problem_id,title,status,owner,hypothesis,evidence_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (item["id"], item["title"], item["status"], item["owner"], item["hypothesis"], json.dumps(item["evidence"], separators=(",", ":")), item["created_at"], now_iso()),
                    )
            if conn.execute("SELECT COUNT(*) FROM improvement_initiatives").fetchone()[0] == 0:
                for item in self.improvement_catalog.get("initiatives", []):
                    conn.execute(
                        """INSERT INTO improvement_initiatives(initiative_id,problem_id,title,status,owner,baseline_metric,baseline_value,target_value,measured_value,unit,hours_saved_monthly,backlog_avoided,sla_improvement_points,confidence_pct,started_at,reviewed_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (item["id"], item.get("problem_id"), item["title"], item["status"], item["owner"], item["baseline_metric"], float(item["baseline_value"]), float(item["target_value"]), float(item["measured_value"]), item["unit"], float(item["hours_saved_monthly"]), int(item["backlog_avoided"]), float(item["sla_improvement_points"]), float(item["confidence_pct"]), item["started_at"], item.get("reviewed_at")),
                    )

    @staticmethod
    def _automation_rule_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["rule_id"], "name": row["name"], "description": row["description"], "enabled": bool(row["enabled"]),
            "severity": row["severity"], "ownerRole": row["owner_role"], "cooldownMinutes": row["cooldown_minutes"], "dedupeKey": row["dedupe_key"],
            "conditions": json.loads(row["conditions_json"]), "action": json.loads(row["action_json"]),
        }

    def list_automation_rules(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM automation_rules ORDER BY severity DESC, rule_id").fetchall()
        return [self._automation_rule_payload(row) for row in rows]

    def list_automation_executions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM automation_executions ORDER BY evaluated_at DESC LIMIT ?", (max(1, min(200, int(limit))),)).fetchall()
        return [{"id": row["execution_id"], "ruleId": row["rule_id"], "evaluatedAt": row["evaluated_at"], "status": row["status"], "reason": row["reason"], "caseId": row["case_id"], "evidence": json.loads(row["evidence_json"])} for row in rows]

    @staticmethod
    def _condition_matches(actual: float, operator: str, expected: float) -> bool:
        return {
            ">": actual > expected, ">=": actual >= expected, "<": actual < expected, "<=": actual <= expected,
            "==": actual == expected, "!=": actual != expected,
        }.get(operator, False)

    def evaluate_automation(self, metrics: dict[str, Any], actor: dict[str, Any], *, execute: bool = False) -> list[dict[str, Any]]:
        numeric: dict[str, float] = {}
        for key, value in metrics.items():
            try:
                parsed = float(value)
                if math.isfinite(parsed): numeric[str(key)] = parsed
            except (TypeError, ValueError):
                continue
        results: list[dict[str, Any]] = []
        for rule in self.list_automation_rules():
            conditions = rule["conditions"]
            matched = bool(rule["enabled"]) and all(
                str(item.get("metric")) in numeric and self._condition_matches(numeric[str(item.get("metric"))], str(item.get("operator")), float(item.get("value")))
                for item in conditions
            )
            evidence = {str(item.get("metric")): numeric.get(str(item.get("metric")), float("nan")) for item in conditions if str(item.get("metric")) in numeric}
            fingerprint = hash_text(json.dumps({"rule": rule["id"], "evidence": evidence}, sort_keys=True, separators=(",", ":")))
            status = "No Match"
            reason = "Conditions did not match the supplied governed metrics."
            case_id: str | None = None
            if matched and not execute:
                status, reason = "Simulated", "Conditions matched; simulation produced no write action."
            elif matched and execute:
                now = datetime.now(UTC)
                with self.connect() as conn:
                    last = conn.execute("SELECT evaluated_at FROM automation_executions WHERE rule_id=? AND status='Triggered' ORDER BY evaluated_at DESC LIMIT 1", (rule["id"],)).fetchone()
                    existing = conn.execute("SELECT case_id FROM workflow_cases WHERE status <> 'Resolved' AND title=? ORDER BY created_at DESC LIMIT 1", (rule["action"]["title"],)).fetchone()
                cooldown_active = bool(last and parse_dt(last["evaluated_at"]) and now - parse_dt(last["evaluated_at"]) < timedelta(minutes=int(rule["cooldownMinutes"])))
                if existing:
                    status, reason, case_id = "Suppressed", "An equivalent open action already exists; duplicate case creation was suppressed.", str(existing["case_id"])
                elif cooldown_active:
                    status, reason = "Suppressed", "Rule matched but the configured cooldown window is still active."
                else:
                    action = rule["action"]
                    created = self.create_case({"title": action["title"], "description": rule["description"], "priority": action["priority"], "owner": action["owner"], "source": f"Automation rule {rule['id']}", "expectedImpact": action["expectedImpact"], "baselineMetric": "Automated operational threshold", "baselineValue": 0, "targetValue": 1, "currentValue": 0, "unit": ""}, actor)
                    case_id = created["id"]
                    status, reason = "Triggered", "Conditions matched and a governed workflow case was created."
            execution_id = f"AUTOEXEC-{rule['id']}-{fingerprint[:12]}-{status.lower().replace(' ', '-') }"
            with self.connect() as conn:
                conn.execute("INSERT OR IGNORE INTO automation_executions(execution_id,rule_id,evaluated_at,status,fingerprint_sha256,reason,evidence_json,case_id) VALUES(?,?,?,?,?,?,?,?)", (execution_id, rule["id"], now_iso(), status, fingerprint, reason, json.dumps(evidence, sort_keys=True, separators=(",", ":")), case_id))
            results.append({"id": execution_id, "ruleId": rule["id"], "evaluatedAt": now_iso(), "status": status, "reason": reason, "caseId": case_id, "evidence": evidence})
        self.add_audit(actor["display_name"], actor["role"], "Automation rules evaluated", "Automation", "closed-loop", f"Mode: {'execute' if execute else 'simulate'}; matched: {sum(1 for item in results if item['status'] in {'Triggered','Simulated','Suppressed'})}.")
        return results

    def list_problems(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM problem_records ORDER BY updated_at DESC").fetchall()
        return [{"id": row["problem_id"], "title": row["title"], "status": row["status"], "owner": row["owner"], "hypothesis": row["hypothesis"], "evidence": json.loads(row["evidence_json"])} for row in rows]

    def list_improvements(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM improvement_initiatives ORDER BY CASE status WHEN 'Active' THEN 1 ELSE 2 END, started_at DESC").fetchall()
        return [{"id": row["initiative_id"], "problemId": row["problem_id"], "title": row["title"], "status": row["status"], "owner": row["owner"], "baselineMetric": row["baseline_metric"], "baselineValue": row["baseline_value"], "targetValue": row["target_value"], "measuredValue": row["measured_value"], "unit": row["unit"], "hoursSavedMonthly": row["hours_saved_monthly"], "backlogAvoided": row["backlog_avoided"], "slaImprovementPoints": row["sla_improvement_points"], "confidencePct": row["confidence_pct"]} for row in rows]

    def value_realization(self) -> dict[str, Any]:
        initiatives = self.list_improvements()
        completed = [item for item in initiatives if item["status"] == "Completed"]
        successful = [item for item in completed if (item["measuredValue"] <= item["targetValue"] if "resolution" in item["baselineMetric"].lower() or "reopen" in item["baselineMetric"].lower() else item["measuredValue"] >= item["targetValue"])]
        return {
            "initiativesActive": sum(1 for item in initiatives if item["status"] == "Active"),
            "initiativesCompleted": len(completed),
            "successful": len(successful),
            "inconclusive": max(0, len(completed) - len(successful)),
            "hoursSavedMonthly": round(sum(float(item["hoursSavedMonthly"]) for item in initiatives), 1),
            "backlogAvoided": int(sum(int(item["backlogAvoided"]) for item in initiatives)),
            "slaImprovementPoints": round(sum(float(item["slaImprovementPoints"]) for item in initiatives), 1),
            "measuredInitiatives": initiatives,
        }

    def list_playbooks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM playbooks ORDER BY playbook_id").fetchall()
        return [{"id": row["playbook_id"], "name": row["name"], "description": row["description"], "steps": json.loads(row["steps_json"])} for row in rows]

    def list_playbook_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM playbook_runs ORDER BY updated_at DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
        return [{"id": row["run_id"], "playbookId": row["playbook_id"], "caseId": row["case_id"], "status": row["status"], "currentStep": row["current_step"], "steps": json.loads(row["steps_json"]), "startedAt": row["started_at"], "updatedAt": row["updated_at"]} for row in rows]

    def start_playbook(self, playbook_id: str, case_id: str | None, actor: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            playbook = conn.execute("SELECT * FROM playbooks WHERE playbook_id=?", (playbook_id,)).fetchone()
            if playbook is None: raise KeyError(playbook_id)
            if case_id and conn.execute("SELECT 1 FROM workflow_cases WHERE case_id=?", (case_id,)).fetchone() is None: raise ValueError("Linked case does not exist.")
            steps = [{"label": label, "completed": False} for label in json.loads(playbook["steps_json"])]
            run_id = f"PBRUN-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
            now = now_iso()
            conn.execute("INSERT INTO playbook_runs(run_id,playbook_id,case_id,status,current_step,steps_json,started_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (run_id, playbook_id, case_id, "Active", 0, json.dumps(steps, separators=(",", ":")), now, now))
        self.add_audit(actor["display_name"], actor["role"], "Playbook started", "Playbook", run_id, f"{playbook_id} linked to {case_id or 'no case'}.")
        return next(item for item in self.list_playbook_runs() if item["id"] == run_id)

    def advance_playbook(self, run_id: str, actor: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM playbook_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None: raise KeyError(run_id)
            steps = json.loads(row["steps_json"])
            current = int(row["current_step"])
            if current < len(steps): steps[current]["completed"] = True
            next_step = min(len(steps), current + 1)
            status = "Completed" if next_step >= len(steps) else "Active"
            conn.execute("UPDATE playbook_runs SET status=?,current_step=?,steps_json=?,updated_at=? WHERE run_id=?", (status, next_step, json.dumps(steps, separators=(",", ":")), now_iso(), run_id))
        self.add_audit(actor["display_name"], actor["role"], "Playbook advanced", "Playbook", run_id, f"Step {next_step} of {len(steps)}; status {status}.")
        return next(item for item in self.list_playbook_runs() if item["id"] == run_id)

    def demo_users(self) -> list[dict[str, str]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT user_id,display_name,role FROM demo_users WHERE enabled=1 ORDER BY role")]

    def create_session(self, user_id: str, password: str, hours: int = 8) -> Session:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        created = datetime.now(UTC)
        expires = created + timedelta(hours=hours)
        with self.connect() as conn:
            user = conn.execute("SELECT user_id,display_name,role,password_salt,password_hash FROM demo_users WHERE user_id=? AND enabled=1", (user_id,)).fetchone()
            if user is None or not verify_password(password, str(user["password_salt"]), str(user["password_hash"])):
                raise PermissionError("Invalid demo credentials.")
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (created.isoformat(),))
            conn.execute(
                "INSERT INTO sessions(token_hash,csrf_hash,user_id,created_at,expires_at) VALUES(?,?,?,?,?)",
                (hash_text(token), hash_text(csrf), user_id, created.isoformat(), expires.isoformat()),
            )
        return Session(user_id=user["user_id"], display_name=user["display_name"], role=user["role"], csrf_token=csrf, token=token, expires_at=expires.isoformat())

    def get_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self.connect() as conn:
            row = conn.execute(
                """SELECT s.token_hash,s.csrf_hash,s.user_id,s.expires_at,u.display_name,u.role
                FROM sessions s JOIN demo_users u ON u.user_id=s.user_id
                WHERE s.token_hash=? AND u.enabled=1""", (hash_text(token),)
            ).fetchone()
            if row is None or parse_dt(row["expires_at"]) is None or parse_dt(row["expires_at"]) <= datetime.now(UTC):
                return None
            return dict(row)

    def validate_csrf(self, session: dict[str, Any] | None, token: str | None) -> bool:
        return bool(session and token and secrets.compare_digest(str(session["csrf_hash"]), hash_text(token)))

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (hash_text(token),))

    def authorize(self, session: dict[str, Any] | None, permission: str) -> bool:
        return bool(session and permission in ROLE_PERMISSIONS.get(str(session.get("role")), set()))

    def add_audit(self, actor: str, actor_role: str, action: str, entity_type: str, entity_id: str, details: str) -> dict[str, Any]:
        audit_id = f"AUD-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        payload = {"id": audit_id, "timestamp": now_iso(), "actor": actor, "action": action, "entityType": entity_type, "entityId": entity_id, "details": details}
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO audit_events(audit_id,event_at,actor,actor_role,action,entity_type,entity_id,details) VALUES(?,?,?,?,?,?,?,?)",
                (audit_id, payload["timestamp"], actor, actor_role, action, entity_type, entity_id, details[:2000]),
            )
        return payload

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(250, int(limit)))
        with self.connect() as conn:
            rows = conn.execute("SELECT audit_id,event_at,actor,action,entity_type,entity_id,details FROM audit_events ORDER BY event_at DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r["audit_id"], "timestamp": r["event_at"], "actor": r["actor"], "action": r["action"], "entityType": r["entity_type"], "entityId": r["entity_id"], "details": r["details"]} for r in rows]

    def list_cases(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM workflow_cases ORDER BY CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, created_at DESC").fetchall()
        return [self._case_payload(r) for r in rows]

    @staticmethod
    def _case_payload(r: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": r["case_id"], "title": r["title"], "description": r["description"], "priority": r["priority"], "status": r["status"],
            "owner": r["owner"], "createdAt": r["created_at"], "dueAt": r["due_at"], "source": r["source"], "expectedImpact": r["expected_impact"],
            "baselineMetric": r["baseline_metric"], "baselineValue": r["baseline_value"], "targetValue": r["target_value"], "currentValue": r["current_value"],
            "unit": r["unit"], "notes": r["notes"],
        }

    def create_case(self, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            number = conn.execute("SELECT COALESCE(MAX(CAST(SUBSTR(case_id,6) AS INTEGER)),0)+1 FROM workflow_cases WHERE case_id GLOB 'CASE-[0-9]*'").fetchone()[0]
            case_id = f"CASE-{int(number):03d}"
            created = now_iso()
            due = str(payload.get("dueAt") or (datetime.now(UTC) + timedelta(days=7)).isoformat())
            values = (
                case_id, str(payload.get("title") or "Untitled operational case")[:180], str(payload.get("description") or "")[:2000],
                str(payload.get("priority") or "Medium"), "Open", str(payload.get("owner") or actor["display_name"])[:120], created, due,
                str(payload.get("source") or "Analytical recommendation")[:220], str(payload.get("expectedImpact") or "")[:500],
                str(payload.get("baselineMetric") or "Operational target")[:120], float(payload.get("baselineValue") or 0), float(payload.get("targetValue") or 0),
                float(payload.get("currentValue") or payload.get("baselineValue") or 0), str(payload.get("unit") or "")[:30], "", created,
            )
            conn.execute("""INSERT INTO workflow_cases(case_id,title,description,priority,status,owner,created_at,due_at,source,expected_impact,baseline_metric,baseline_value,target_value,current_value,unit,notes,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            row = conn.execute("SELECT * FROM workflow_cases WHERE case_id=?", (case_id,)).fetchone()
        self.add_audit(actor["display_name"], actor["role"], "Case created", "Case", case_id, f"Created governed case: {values[1]}")
        return self._case_payload(row)

    def update_case(self, case_id: str, changes: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        allowed = {"status": "status", "owner": "owner", "notes": "notes", "currentValue": "current_value", "dueAt": "due_at"}
        assignments: list[str] = []
        values: list[Any] = []
        for key, column in allowed.items():
            if key not in changes:
                continue
            value: Any = changes[key]
            if key == "status" and value not in {"Open", "In Progress", "Monitoring", "Resolved"}:
                raise ValueError("Unsupported case status.")
            if key == "currentValue":
                value = float(value)
            else:
                value = str(value)[:2000 if key == "notes" else 160]
            assignments.append(f"{column}=?")
            values.append(value)
        if not assignments:
            raise ValueError("No supported case fields were supplied.")
        assignments.append("updated_at=?")
        values.append(now_iso())
        values.append(case_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE workflow_cases SET {', '.join(assignments)} WHERE case_id=?", values)
            row = conn.execute("SELECT * FROM workflow_cases WHERE case_id=?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        self.add_audit(actor["display_name"], actor["role"], "Case updated", "Case", case_id, "Updated fields: " + ", ".join(sorted(k for k in changes if k in allowed)))
        return self._case_payload(row)

    def record_outcome(self, case_id: str, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        result = str(payload.get("result") or "Insufficient data")
        if result not in {"Improved", "Mixed", "Insufficient data"}:
            raise ValueError("Unsupported outcome result.")
        outcome_id = f"OUT-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        measured = now_iso()
        with self.connect() as conn:
            case = conn.execute("SELECT * FROM workflow_cases WHERE case_id=?", (case_id,)).fetchone()
            if case is None:
                raise KeyError(case_id)
            conn.execute(
                "INSERT INTO action_outcomes(outcome_id,case_id,metric,baseline_value,measured_value,target_value,unit,measured_at,result,notes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (outcome_id, case_id, str(payload.get("metric") or case["baseline_metric"]), float(payload.get("baselineValue") or case["baseline_value"]),
                 float(payload.get("measuredValue") or case["current_value"]), float(payload.get("targetValue") or case["target_value"]),
                 str(payload.get("unit") or case["unit"]), measured, result, str(payload.get("notes") or "")[:2000]),
            )
        self.add_audit(actor["display_name"], actor["role"], "Outcome recorded", "Case", case_id, f"Measured result: {result}")
        return {"id": outcome_id, "caseId": case_id, "result": result, "measuredAt": measured}

    def list_outcomes(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM action_outcomes ORDER BY measured_at DESC").fetchall()
        return [dict(r) for r in rows]

    def list_kpis(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("""SELECT d.kpi_id,d.name,d.owner,d.current_version,v.effective_date,v.definition,v.formula,v.grain,v.window_text,v.target,v.source_fields_json,v.limitations
            FROM kpi_definitions d JOIN kpi_versions v ON v.kpi_id=d.kpi_id AND v.version=d.current_version ORDER BY d.name""").fetchall()
        return [{
            "id": r["kpi_id"], "name": r["name"], "owner": r["owner"], "version": r["current_version"], "effectiveDate": r["effective_date"],
            "definition": r["definition"], "formula": r["formula"], "grain": r["grain"], "window": r["window_text"], "target": r["target"],
            "sourceFields": json.loads(r["source_fields_json"]), "limitations": r["limitations"],
        } for r in rows]

    def create_kpi_version(self, kpi_id: str, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        version = str(payload.get("version") or "").strip()
        if not version or len(version) > 32:
            raise ValueError("A bounded KPI version is required.")
        with self.connect() as conn:
            definition = conn.execute("SELECT * FROM kpi_definitions WHERE kpi_id=?", (kpi_id,)).fetchone()
            if definition is None:
                raise KeyError(kpi_id)
            current = conn.execute("SELECT * FROM kpi_versions WHERE kpi_id=? AND version=?", (kpi_id, definition["current_version"])).fetchone()
            fields = payload.get("sourceFields") if isinstance(payload.get("sourceFields"), list) else json.loads(current["source_fields_json"])
            conn.execute("""INSERT INTO kpi_versions(kpi_id,version,effective_date,definition,formula,grain,window_text,target,source_fields_json,limitations,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (
                kpi_id, version, str(payload.get("effectiveDate") or datetime.now(UTC).date()), str(payload.get("definition") or current["definition"])[:2000],
                str(payload.get("formula") or current["formula"])[:2000], str(payload.get("grain") or current["grain"])[:200],
                str(payload.get("window") or current["window_text"])[:200], str(payload.get("target") or current["target"])[:300],
                json.dumps(fields), str(payload.get("limitations") or current["limitations"])[:2000], actor["display_name"], now_iso()))
            conn.execute("UPDATE kpi_definitions SET current_version=? WHERE kpi_id=?", (version, kpi_id))
        self.add_audit(actor["display_name"], actor["role"], "KPI version published", "KPI", kpi_id, f"Published version {version}")
        return next(item for item in self.list_kpis() if item["id"] == kpi_id)

    def record_backtest(self, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        horizon = int(payload.get("horizonDays") or 0)
        mae = float(payload.get("meanAbsoluteError") or 0)
        bias = float(payload.get("meanBias") or 0)
        observed = float(payload.get("observedDailyFlow") or 0)
        model = str(payload.get("modelVersion") or "").strip()[:120]
        if horizon < 7 or horizon > 365 or not model:
            raise ValueError("Backtest horizon and model version are required and bounded.")
        if not all(math.isfinite(value) and abs(value) <= 1_000_000 for value in (mae, bias, observed)) or mae < 0 or observed < 0:
            raise ValueError("Backtest metrics must be finite and within portfolio-demo bounds.")
        with self.connect() as conn:
            latest = conn.execute("SELECT run_id FROM ingestion_runs WHERE status='accepted' ORDER BY loaded_at DESC LIMIT 1").fetchone()
            run_id = str(latest["run_id"]) if latest else None
        signature_payload = {"run":run_id,"horizon":horizon,"mae":round(mae,6),"bias":round(bias,6),"observed":round(observed,6),"model":model}
        signature = sha256_bytes(json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        created = now_iso()
        backtest_id = f"BT-{signature[:16].upper()}"
        created_new = False
        with self.connect() as conn:
            existing = conn.execute("SELECT * FROM forecast_backtests WHERE signature_sha256=?", (signature,)).fetchone()
            if existing is None:
                conn.execute("""INSERT INTO forecast_backtests(backtest_id,signature_sha256,created_at,dataset_run_id,horizon_days,mean_absolute_error,mean_bias,observed_daily_flow,model_version,details_json)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (backtest_id,signature,created,run_id,horizon,mae,bias,observed,model,json.dumps(payload.get("details") or {}, separators=(",", ":"))))
                idempotent = False
                created_new = True
            else:
                backtest_id = str(existing["backtest_id"]); created = str(existing["created_at"]); idempotent = True
        if created_new:
            self.add_audit(actor["display_name"], actor["role"], "Forecast backtest recorded", "Forecast", backtest_id, f"{model}; MAE {mae:.2f}; bias {bias:.2f}.")
        return {"id":backtest_id,"createdAt":created,"datasetRunId":run_id,"horizonDays":horizon,"meanAbsoluteError":mae,"meanBias":bias,"observedDailyFlow":observed,"modelVersion":model,"idempotent":idempotent}

    def list_backtests(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM forecast_backtests ORDER BY created_at DESC LIMIT ?", (max(1,min(100,limit)),)).fetchall()
        return [{"id":r["backtest_id"],"createdAt":r["created_at"],"datasetRunId":r["dataset_run_id"],"horizonDays":r["horizon_days"],"meanAbsoluteError":r["mean_absolute_error"],"meanBias":r["mean_bias"],"observedDailyFlow":r["observed_daily_flow"],"modelVersion":r["model_version"]} for r in rows]

    def _quality_issue(self, row_number: int, request_id: str, rule: str, field: str, severity: str, message: str, value: Any) -> dict[str, Any]:
        return {"id": f"{rule}-{row_number}-{field}", "rowNumber": row_number, "requestId": request_id or "(missing)", "ruleId": rule, "field": field, "severity": severity, "message": message, "value": str(value or "")}

    def validate_rows(self, rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[bool], float, int]:
        issues: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        blocking = set(self.contract["blocking_rules"])
        trusted_flags: list[bool] = []
        controlled = self.contract["controlled_values"]
        duplicate_count = 0
        per_row: dict[int, list[dict[str, Any]]] = {}

        def add(row_number: int, request_id: str, rule: str, field: str, severity: str, message: str, value: Any) -> None:
            item = self._quality_issue(row_number, request_id, rule, field, severity, message, value)
            issues.append(item)
            per_row.setdefault(row_number, []).append(item)

        for idx, row in enumerate(rows, start=2):
            rid = (row.get("request_id") or "").strip()
            created = parse_dt(row.get("created_at")); closed = parse_dt(row.get("closed_at")); updated = parse_dt(row.get("last_updated_at"))
            status=(row.get("status") or "").strip(); category=(row.get("category") or "").strip(); priority=(row.get("priority") or "").strip()
            team=(row.get("team") or "").strip(); location=(row.get("location") or "").strip(); owner=(row.get("owner") or "").strip()
            sla=as_float(row.get("sla_hours")); resolution=as_float(row.get("resolution_hours")); satisfaction=as_float(row.get("satisfaction_score"))
            if not rid: add(idx,rid,"required-id","request_id","Critical","Request ID is required.",rid)
            if not created: add(idx,rid,"valid-created","created_at","Critical","Created timestamp is missing or invalid.",row.get("created_at"))
            if not status: add(idx,rid,"required-status","status","High","Status is required.",status)
            if not category: add(idx,rid,"required-category","category","High","Category is required.",category)
            if not location: add(idx,rid,"required-location","location","Medium","Location is required for geographic analysis.",location)
            if not team: add(idx,rid,"required-team","team","High","Team is required for accountability reporting.",team)
            if not owner: add(idx,rid,"required-owner","owner","Medium","Owner is required for work assignment.",owner)
            if category not in controlled["category"]: add(idx,rid,"known-category","category","High","Category is not mapped to the controlled taxonomy.",category)
            if priority not in controlled["priority"]: add(idx,rid,"known-priority","priority","High","Priority is not recognized.",priority)
            if status not in controlled["status"]: add(idx,rid,"known-status","status","High","Status is not recognized.",status)
            if sla is None or sla <= 0: add(idx,rid,"valid-sla","sla_hours","High","SLA hours must be a positive number.",row.get("sla_hours"))
            if satisfaction is not None and not 1 <= satisfaction <= 5: add(idx,rid,"valid-satisfaction","satisfaction_score","Medium","Satisfaction score must be between 1 and 5.",satisfaction)
            if created and closed and closed < created: add(idx,rid,"chronology","closed_at","Critical","Closed timestamp occurs before created timestamp.",row.get("closed_at"))
            if status == "Closed" and not closed: add(idx,rid,"closed-consistency","closed_at","High","Closed records require a closed timestamp.",row.get("closed_at"))
            if status != "Closed" and closed: add(idx,rid,"open-consistency","closed_at","Medium","Open records should not have a closed timestamp.",row.get("closed_at"))
            if resolution is not None and resolution < 0: add(idx,rid,"valid-resolution","resolution_hours","Critical","Resolution hours cannot be negative.",resolution)
            if not updated: add(idx,rid,"valid-updated","last_updated_at","Medium","Last-updated timestamp is missing or invalid.",row.get("last_updated_at"))
            if rid:
                if rid in seen:
                    duplicate_count += 1; add(idx,rid,"unique-id","request_id","Critical",f"Duplicate request ID; first seen on row {seen[rid]}.",rid)
                else: seen[rid]=idx

        for idx in range(2, len(rows)+2):
            row_issues = per_row.get(idx, [])
            trusted_flags.append(not any(item["ruleId"] in blocking or item["severity"] == "Critical" for item in row_issues))
        total = max(len(rows), 1)
        weighted = sum(SEVERITY_WEIGHT.get(item["severity"], 0.75) for item in issues)
        score = max(0.0, round((1 - weighted / (total * 4.0)) * 1000) / 10)
        return issues, trusted_flags, score, duplicate_count

    def ingest_csv(self, csv_text: str, dataset_name: str, source_name: str, actor: dict[str, Any] | None = None) -> dict[str, Any]:
        raw_bytes = csv_text.encode("utf-8")
        digest = sha256_bytes(raw_bytes)
        with self.connect() as conn:
            prior = conn.execute("SELECT * FROM ingestion_runs WHERE content_sha256=? AND status='accepted' ORDER BY loaded_at DESC LIMIT 1", (digest,)).fetchone()
            if prior is not None:
                return {"runId": prior["run_id"], "status": "unchanged", "idempotent": True, "qualityScore": prior["quality_score"], "rowCount": prior["row_count"], "trustedRowCount": prior["trusted_row_count"], "issueRowCount": prior["issue_row_count"], "unexpectedColumns": json.loads(prior["unexpected_columns_json"]), "missingColumns": []}

        reader = csv.DictReader(io.StringIO(csv_text))
        headers = [str(item or "").strip().lower() for item in (reader.fieldnames or [])]
        required = list(self.contract["required_columns"])
        missing = [name for name in required if name not in headers]
        unexpected = [name for name in headers if name and name not in required]
        run_id = f"ING-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        loaded = now_iso()
        if missing:
            with self.connect() as conn:
                conn.execute("""INSERT INTO ingestion_runs(run_id,dataset_name,source_name,content_sha256,contract_version,status,loaded_at,missing_columns_json,unexpected_columns_json,notes)
                VALUES(?,?,?,?,?,'rejected',?,?,?,?)""", (run_id, dataset_name[:180], source_name[:180], digest, int(self.contract["schema_version"]), loaded, json.dumps(missing), json.dumps(unexpected), "Missing required columns."))
            if actor: self.add_audit(actor["display_name"], actor["role"], "Dataset rejected", "Ingestion", run_id, "Missing required columns: " + ", ".join(missing))
            return {"runId": run_id, "status": "rejected", "idempotent": False, "missingColumns": missing, "unexpectedColumns": unexpected, "rowCount": 0, "trustedRowCount": 0, "issueRowCount": 0, "qualityScore": 0.0}

        rows: list[dict[str, str]] = []
        for source in reader:
            rows.append({key.strip().lower(): (value or "").strip() for key, value in source.items() if key is not None})
        issues, trusted_flags, score, duplicate_count = self.validate_rows(rows)
        trusted_count = sum(1 for value in trusted_flags if value)
        issue_rows = len({int(item["rowNumber"]) for item in issues})
        max_updated = max((parse_dt(row.get("last_updated_at")) for row in rows if parse_dt(row.get("last_updated_at"))), default=None)
        with self.connect() as conn:
            conn.execute("""INSERT INTO ingestion_runs(run_id,dataset_name,source_name,content_sha256,contract_version,status,loaded_at,row_count,trusted_row_count,issue_row_count,duplicate_row_count,quality_score,unexpected_columns_json,missing_columns_json,source_max_updated_at,notes)
            VALUES(?,?,?,?,?,'accepted',?,?,?,?,?,?,?,?,?,?)""", (
                run_id,dataset_name[:180],source_name[:180],digest,int(self.contract["schema_version"]),loaded,len(rows),trusted_count,issue_rows,duplicate_count,score,json.dumps(unexpected),json.dumps([]),max_updated.isoformat() if max_updated else None,
                "Unexpected columns were accepted and flagged." if unexpected else "Contract matched required schema."))
            for item in issues:
                conn.execute("INSERT INTO ingestion_issues(issue_id,run_id,row_number,request_id,rule_id,field_name,severity,message,value_text) VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"{run_id}-{item['id']}",run_id,item["rowNumber"],item["requestId"],item["ruleId"],item["field"],item["severity"],item["message"],item["value"][:1000]))
            for offset, row in enumerate(rows):
                row_number = offset + 2
                conn.execute("""INSERT INTO service_requests(run_id,row_number,request_id,created_at,closed_at,status,priority,category,subcategory,location,team,owner,channel,sla_hours,resolution_hours,reopened,satisfaction_score,last_updated_at,source_system,trusted,raw_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    run_id,row_number,row.get("request_id","")[:180],row.get("created_at") or None,row.get("closed_at") or None,row.get("status","")[:100],row.get("priority","")[:100],row.get("category","")[:180],row.get("subcategory","")[:180],row.get("location","")[:180],row.get("team","")[:180],row.get("owner","")[:180],row.get("channel","")[:100],as_float(row.get("sla_hours")),as_float(row.get("resolution_hours")),1 if bool_value(row.get("reopened")) else 0,as_float(row.get("satisfaction_score")),row.get("last_updated_at") or None,row.get("source_system","")[:180],1 if trusted_flags[offset] else 0,json.dumps(row,ensure_ascii=False,separators=(",",":"))))
        if actor: self.add_audit(actor["display_name"], actor["role"], "Dataset ingested", "Ingestion", run_id, f"{len(rows)} rows; {trusted_count} trusted; quality {score:.1f}%.")
        return {"runId":run_id,"status":"accepted","idempotent":False,"qualityScore":score,"rowCount":len(rows),"trustedRowCount":trusted_count,"issueRowCount":issue_rows,"duplicateRowCount":duplicate_count,"unexpectedColumns":unexpected,"missingColumns":[],"sourceMaxUpdatedAt":max_updated.isoformat() if max_updated else None}

    def ensure_demo_ingested(self) -> dict[str, Any]:
        snapshot = read_snapshot("demo-local")
        return self.ingest_csv(snapshot.csv_text, snapshot.dataset_name, snapshot.source_name)

    def run_scheduled_refresh(self, force: bool = False) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self.connect() as conn:
            schedule = conn.execute("SELECT * FROM refresh_schedule WHERE schedule_id='demo-local'").fetchone()
            if schedule is None or not schedule["enabled"]:
                return {"status":"disabled"}
            due = parse_dt(schedule["next_due_at"]) or now
            if not force and due > now:
                return {"status":"not_due","nextDueAt":due.isoformat()}
        snapshot = read_snapshot(str(schedule["connector_id"]))
        result = self.ingest_csv(snapshot.csv_text, snapshot.dataset_name, snapshot.source_name)
        next_due = now + timedelta(minutes=int(schedule["interval_minutes"]))
        with self.connect() as conn:
            conn.execute("UPDATE refresh_schedule SET last_checked_at=?,last_result=?,next_due_at=? WHERE schedule_id='demo-local'", (now.isoformat(), result["status"], next_due.isoformat()))
        return {**result,"nextDueAt":next_due.isoformat()}

    def latest_ingestions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM ingestion_runs ORDER BY loaded_at DESC LIMIT ?", (max(1,min(100,limit)),)).fetchall()
        return [{"runId":r["run_id"],"datasetName":r["dataset_name"],"sourceName":r["source_name"],"status":r["status"],"loadedAt":r["loaded_at"],"rowCount":r["row_count"],"trustedRowCount":r["trusted_row_count"],"issueRowCount":r["issue_row_count"],"qualityScore":r["quality_score"],"unexpectedColumns":json.loads(r["unexpected_columns_json"])} for r in rows]

    def observability(self, release_passed: bool = True) -> dict[str, Any]:
        with self.connect() as conn:
            latest = conn.execute("SELECT * FROM ingestion_runs WHERE status='accepted' ORDER BY loaded_at DESC LIMIT 1").fetchone()
            quality_rows = conn.execute("SELECT loaded_at,quality_score,trusted_row_count,row_count FROM ingestion_runs WHERE status='accepted' ORDER BY loaded_at DESC LIMIT 10").fetchall()
            recent = conn.execute("SELECT status,COUNT(*) n FROM ingestion_runs GROUP BY status").fetchall()
            cases = conn.execute("SELECT status,COUNT(*) n FROM workflow_cases GROUP BY status").fetchall()
            outcomes = conn.execute("SELECT result,COUNT(*) n FROM action_outcomes GROUP BY result").fetchall()
            feedback = conn.execute("SELECT COUNT(*) reviewed,COALESCE(SUM(confirmed_signal),0) confirmed,COALESCE(SUM(useful),0) useful FROM alert_feedback").fetchone()
            schedule = conn.execute("SELECT * FROM refresh_schedule WHERE schedule_id='demo-local'").fetchone()
        status_counts = {r["status"]: r["n"] for r in recent}; case_counts={r["status"]:r["n"] for r in cases}; outcome_counts={r["result"]:r["n"] for r in outcomes}
        accepted = status_counts.get("accepted",0); rejected=status_counts.get("rejected",0); denominator=max(accepted+rejected,1)
        ingestion_success = accepted/denominator*100
        freshness_minutes = (datetime.now(UTC) - (parse_dt(latest["loaded_at"]) if latest else datetime.fromtimestamp(0,UTC))).total_seconds()/60 if latest else 999999
        total_cases=sum(case_counts.values()); progressed=total_cases-case_counts.get("Open",0); follow=progressed/max(total_cases,1)*100
        total_outcomes=sum(outcome_counts.values()); improve=outcome_counts.get("Improved",0)/max(total_outcomes,1)*100
        reviewed=int(feedback["reviewed"] if feedback else 0); precision=(int(feedback["confirmed"])/max(reviewed,1)*100); usefulness=(int(feedback["useful"])/max(reviewed,1)*100)
        duplicate_reprocessed = 0
        quality_history=[{"loadedAt":r["loaded_at"],"qualityScore":r["quality_score"],"trustedRowCount":r["trusted_row_count"],"rowCount":r["row_count"]} for r in reversed(quality_rows)]
        prior_quality=float(quality_rows[1]["quality_score"]) if len(quality_rows)>1 else None
        current_quality=float(latest["quality_score"]) if latest else 0.0
        quality_delta=round(current_quality-prior_quality,1) if prior_quality is not None else None
        measurements = [
            {"id":"release_gate","name":"Release identity gate","value":100.0 if release_passed else 0.0,"unit":"%","target":"100% pass","status":"Healthy" if release_passed else "Breach","details":"Version/build/manifest/package hashes must agree before serving."},
            {"id":"ingestion_success","name":"Ingestion success rate","value":round(ingestion_success,1),"unit":"%","target":">= 99%","status":"Healthy" if ingestion_success>=99 else "Watch","details":f"Accepted {accepted}; rejected {rejected}."},
            {"id":"ingestion_freshness","name":"Governed ingestion freshness","value":round(freshness_minutes,1),"unit":" min","target":"<= 360 minutes","status":"Healthy" if freshness_minutes<=360 else "Watch","details":"Measured from the latest successful governed local ingestion."},
            {"id":"data_quality","name":"Data-quality score","value":round(current_quality,1),"unit":"%","target":">= 95%","status":"Healthy" if latest and current_quality>=95 else "Watch","details":f"Trusted rows: {latest['trusted_row_count'] if latest else 0}; movement: {quality_delta:+.1f} pts vs prior accepted run." if quality_delta is not None else f"Trusted rows: {latest['trusted_row_count'] if latest else 0}; first accepted run establishes the trend baseline."},
            {"id":"alert_review","name":"Reviewed alert precision / usefulness","value":round(precision,1),"unit":"%","target":">= 75% confirmed signal and >= 75% useful","status":"Healthy" if precision>=75 and usefulness>=75 else "Watch","details":f"{int(feedback['confirmed']) if feedback else 0}/{reviewed} confirmed signals; {int(feedback['useful']) if feedback else 0}/{reviewed} rated useful. Synthetic review evidence is explicitly seeded for the portfolio demo."},
            {"id":"case_followthrough","name":"Case follow-through","value":round(follow,1),"unit":"%","target":">= 80% beyond Open","status":"Healthy" if follow>=80 else "Watch","details":f"{progressed} of {total_cases} cases moved beyond Open."},
            {"id":"duplicate_processing","name":"Duplicate ingestion processing","value":float(duplicate_reprocessed),"unit":" datasets","target":"0 duplicate datasets reprocessed","status":"Healthy","details":"Content SHA-256 makes identical loads idempotent."},
        ]
        backtests=self.list_backtests(1)
        return {"measuredAt":now_iso(),"measurements":measurements,"measuredImprovementRate":round(improve,1),"latestIngestion":self.latest_ingestions(1)[0] if latest else None,"qualityHistory":quality_history,"alertReview":{"reviewed":reviewed,"confirmedSignals":int(feedback["confirmed"] if feedback else 0),"useful":int(feedback["useful"] if feedback else 0),"precisionPct":round(precision,1),"usefulnessPct":round(usefulness,1)},"latestBacktest":backtests[0] if backtests else None,"refreshSchedule":{"enabled":bool(schedule["enabled"]) if schedule else False,"nextDueAt":schedule["next_due_at"] if schedule else None,"lastResult":schedule["last_result"] if schedule else None},"database":{"engine":"SQLite","journalMode":"WAL","location":"project-local state/operations_intelligence.db"}}


def main() -> int:
    store = OperationalStore()
    refresh = store.run_scheduled_refresh(force=True)
    print(json.dumps({"db": str(store.db_path), "migrations": "current", "refresh": refresh, "observability": store.observability()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
