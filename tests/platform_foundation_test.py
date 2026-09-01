#!/usr/bin/env python3
"""Foundation tests for migrations, governed ingestion, RBAC, KPI lineage, and durable evaluation."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from operational_store import DEMO_CSV, DEMO_PASSWORD, OperationalStore  # noqa: E402
from platform_api import PlatformApi  # noqa: E402
from source_connectors import load_registry, read_snapshot  # noqa: E402

REPORT = ROOT / "reports" / "platform_foundation_test_report.json"


def main() -> int:
    tests: list[dict[str, Any]] = []

    def check(name: str, condition: bool, details: Any = None) -> None:
        tests.append({"name": name, "passed": bool(condition), "details": details})

    with tempfile.TemporaryDirectory(prefix="oiap-platform-test-") as temp_dir:
        db_path = Path(temp_dir) / "operations.db"
        store = OperationalStore(db_path)

        with store.connect() as conn:
            migrations = [int(row[0]) for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            user_count = int(conn.execute("SELECT COUNT(*) FROM demo_users WHERE enabled=1").fetchone()[0])
            table_names = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        check("controlled migrations applied", migrations == [1, 2, 3, 4], migrations)
        check("SQLite uses WAL journal mode", journal == "wal", journal)
        check("four enabled demo identities seeded", user_count == 4, user_count)
        check("operational schema contains no unused SLO snapshot table", "slo_measurements" not in table_names, sorted(table_names))
        check("closed-loop schema includes automation, problems, improvements, and playbooks", {"automation_rules", "automation_executions", "problem_records", "improvement_initiatives", "playbooks", "playbook_runs"}.issubset(table_names), sorted(table_names))

        registry = load_registry()
        snapshot = read_snapshot("demo-local")
        check("source-adapter registry has one bounded canonical adapter", set(registry) == {"demo-local"} and registry["demo-local"].get("type") == "local_csv" and snapshot.byte_count > 0, {"connectors": sorted(registry), "bytes": snapshot.byte_count})
        with store.connect() as conn:
            connector_id = str(conn.execute("SELECT connector_id FROM refresh_schedule WHERE schedule_id='demo-local'").fetchone()[0])
        check("scheduled refresh resolves through the source-adapter registry", connector_id == "demo-local", connector_id)

        try:
            store.create_session("exec-demo", "wrong-password")
            wrong_rejected = False
        except PermissionError:
            wrong_rejected = True
        check("invalid demo credentials rejected", wrong_rejected)

        executive_session = store.create_session("exec-demo", DEMO_PASSWORD)
        executive = store.get_session(executive_session.token)
        operator_session = store.create_session("operator-demo", DEMO_PASSWORD)
        operator = store.get_session(operator_session.token)
        steward_session = store.create_session("steward-demo", DEMO_PASSWORD)
        steward = store.get_session(steward_session.token)
        check("valid credential creates hashed server session", bool(executive) and executive.get("role") == "Executive")
        check("CSRF token validates only for session", store.validate_csrf(executive, executive_session.csrf_token) and not store.validate_csrf(executive, "wrong"))
        check("RBAC separates operator, automation, and stewardship permissions", bool(operator) and store.authorize(operator, "manage_cases") and store.authorize(operator, "read_automation") and not store.authorize(operator, "run_automation") and not store.authorize(operator, "read_governance") and bool(steward) and store.authorize(steward, "manage_kpis") and store.authorize(steward, "run_automation") and not store.authorize(steward, "manage_cases"))

        csv_text = DEMO_CSV.read_text(encoding="utf-8")
        first = store.ingest_csv(csv_text, "Synthetic Service Operations Demo", "platform test", executive)
        second = store.ingest_csv(csv_text, "Synthetic Service Operations Demo", "platform test", executive)
        check("governed ingestion reproduces source population", first.get("rowCount") == 1354 and first.get("trustedRowCount") == 1335, first)
        check("governed quality score reproduces browser result", abs(float(first.get("qualityScore", 0)) - 97.6) < 0.001, first.get("qualityScore"))
        check("identical content load is idempotent", second.get("status") == "unchanged" and second.get("idempotent") is True and second.get("runId") == first.get("runId"), second)

        lines = csv_text.splitlines()
        drifted = lines[0] + ",unexpected_demo_field\n" + "\n".join(line + ",demo" for line in lines[1:]) + "\n"
        drift = store.ingest_csv(drifted, "Drifted synthetic demo", "platform test", executive)
        check("non-breaking schema drift is accepted and flagged", drift.get("status") == "accepted" and "unexpected_demo_field" in drift.get("unexpectedColumns", []), drift.get("unexpectedColumns"))

        missing_header = lines[0].replace(",source_system", "")
        missing = missing_header + "\n" + "\n".join(",".join(line.split(",")[:-1]) for line in lines[1:20]) + "\n"
        rejected = store.ingest_csv(missing, "Missing-column demo", "platform test", executive)
        check("breaking contract drift is rejected", rejected.get("status") == "rejected" and "source_system" in rejected.get("missingColumns", []), rejected.get("missingColumns"))

        kpis = store.list_kpis()
        check("versioned KPI semantic layer seeded", len(kpis) >= 6 and all(item.get("version") == "1.0.0" for item in kpis), [item.get("id") for item in kpis])
        published = store.create_kpi_version("open_backlog", {"version": "1.1.0", "target": "<= 35 requests", "effectiveDate": "2026-08-29"}, steward)
        check("data steward can publish an auditable KPI version", published.get("version") == "1.1.0" and published.get("target") == "<= 35 requests", published)

        new_case = store.create_case({"title": "Foundation test case", "owner": "Operations Analyst", "baselineValue": 10, "targetValue": 8, "currentValue": 9, "unit": "%"}, executive)
        outcome = store.record_outcome(new_case["id"], {"result": "Improved", "measuredValue": 7.5, "notes": "Synthetic platform test outcome."}, executive)
        check("workflow action and measured outcome persist", new_case["id"].startswith("CASE-") and outcome.get("result") == "Improved")

        backtest_payload = {"horizonDays": 28, "meanAbsoluteError": 2.4, "meanBias": -0.3, "observedDailyFlow": 3.2, "modelVersion": "seasonal-capacity-v2"}
        backtest_1 = store.record_backtest(backtest_payload, executive)
        backtest_2 = store.record_backtest(backtest_payload, executive)
        check("forecast backtest evidence is durable and idempotent", backtest_1["id"] == backtest_2["id"] and backtest_2["idempotent"] is True, backtest_2)

        rules = store.list_automation_rules()
        check("closed-loop automation catalog seeds governed trigger-logic-action rules", len(rules) == 3 and all(item.get("conditions") and item.get("action") for item in rules), [item.get("id") for item in rules])
        automation_metrics = {"backlogChangePct": 76.2, "slaAttainmentPct": 56.1, "trustedRows": 1335, "qualityScore": 97.6, "issueRowCount": 45, "closureToIntakeRatio": 0.84, "openBacklog": 37}
        simulated = store.evaluate_automation(automation_metrics, executive, execute=False)
        check("automation engine supports no-write simulation", len(simulated) == 3 and all(item["status"] == "Simulated" for item in simulated), simulated)
        executed = store.evaluate_automation(automation_metrics, executive, execute=True)
        check("governed automation creates bounded workflow actions", len(executed) == 3 and all(item["status"] == "Triggered" and item.get("caseId") for item in executed), executed)
        suppressed = store.evaluate_automation(automation_metrics, executive, execute=True)
        check("automation dedupe and cooldown suppress repeated work", len(suppressed) == 3 and all(item["status"] == "Suppressed" for item in suppressed), suppressed)

        problems = store.list_problems()
        initiatives = store.list_improvements()
        value = store.value_realization()
        check("problem management and improvement initiatives are durable", len(problems) >= 2 and len(initiatives) >= 3 and value["initiativesCompleted"] >= 2, {"problems": len(problems), "initiatives": len(initiatives), "value": value})
        check("value realization exposes synthetic measured outcomes without guarantees", value["hoursSavedMonthly"] > 0 and value["backlogAvoided"] > 0 and value["slaImprovementPoints"] > 0, value)

        playbooks = store.list_playbooks()
        run = store.start_playbook(playbooks[0]["id"], new_case["id"], executive)
        advanced = store.advance_playbook(run["id"], executive)
        check("guided playbooks persist auditable progress", len(playbooks) == 3 and run["status"] == "Active" and advanced["currentStep"] == 1 and advanced["steps"][0]["completed"] is True, advanced)

        snapshot = store.observability(True)
        ids = {item["id"] for item in snapshot["measurements"]}
        check("observability covers release, ingestion, quality, alerts, workflow, and duplicate processing", {"release_gate", "ingestion_success", "ingestion_freshness", "data_quality", "alert_review", "case_followthrough", "duplicate_processing"}.issubset(ids), sorted(ids))
        check("reviewed synthetic alert evidence is explicit", snapshot["alertReview"]["reviewed"] == 4 and snapshot["alertReview"]["precisionPct"] == 75.0 and snapshot["alertReview"]["usefulnessPct"] == 75.0, snapshot["alertReview"])
        check("data-quality history and latest backtest are exposed", len(snapshot["qualityHistory"]) >= 2 and snapshot["latestBacktest"] is not None, {"qualityHistory": len(snapshot["qualityHistory"]), "latestBacktest": snapshot["latestBacktest"]})

        # API service checks without an HTTP server: auth, content type, origin, RBAC and CSRF.
        api = PlatformApi(store, release_passed=True)
        invalid_type = api.handle_post("/api/auth/demo-login", {"Host": "127.0.0.1:8765", "Content-Type": "text/plain"}, b"{}")
        check("governed writes require JSON", invalid_type is not None and invalid_type.status == 415, invalid_type.status if invalid_type else None)
        bad_origin = api.handle_post("/api/auth/demo-login", {"Host": "127.0.0.1:8765", "Origin": "https://example.invalid", "Content-Type": "application/json"}, json.dumps({"userId": "exec-demo", "password": DEMO_PASSWORD}).encode())
        check("cross-site governed login rejected", bad_origin is not None and bad_origin.status == 403, bad_origin.status if bad_origin else None)

    failed = [item for item in tests if not item["passed"]]
    metadata = json.loads((ROOT / "PACKAGE_METADATA.json").read_text(encoding="utf-8"))
    payload = {
        "schema_version": 1,
        "project": "Operations Intelligence & Automation Platform",
        "version": (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(),
        "build": metadata.get("build"),
        "passed": not failed,
        "test_count": len(tests),
        "passed_count": len(tests) - len(failed),
        "failed_count": len(failed),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": tests,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_name(f".{REPORT.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(REPORT)
    print(f"{payload['passed_count']}/{payload['test_count']} platform foundation checks passed.")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
