#!/usr/bin/env python3
"""Negative and positive tests for the one-active-launcher release contract."""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verify_release import EXPECTED_MANAGED_ROOTS, EXPECTED_MANAGED_RUNTIME_FILES, active_launcher_contract  # noqa: E402

REPORT = ROOT / "reports" / "release_contract_test_report.json"


def main() -> int:
    metadata = json.loads((ROOT / "PACKAGE_METADATA.json").read_text(encoding="utf-8"))
    cases: list[dict[str, object]] = []

    def case(name: str, condition: bool, result: dict[str, object]) -> None:
        cases.append({"name": name, "passed": bool(condition), "details": result})

    actual = active_launcher_contract(metadata)
    case("actual package has one approved active launcher contract", bool(actual.get("passed")), actual)

    duplicate = active_launcher_contract(metadata, ["OperationsIntelligence.bat", "operationsintelligence.CMD"])
    case("case-insensitive extra launcher fails closed", not bool(duplicate.get("passed")), duplicate)

    missing = active_launcher_contract(metadata, [])
    case("missing canonical launcher fails closed", not bool(missing.get("passed")), missing)

    bad_alias_metadata = copy.deepcopy(metadata)
    execution = bad_alias_metadata.setdefault("execution", {})
    execution["approved_launcher_files"] = ["OperationsIntelligence.bat", "LegacyStart.cmd"]
    execution["approved_aliases"] = [{"file": "LegacyStart.cmd", "consumers": []}]
    bad_alias = active_launcher_contract(bad_alias_metadata, ["OperationsIntelligence.bat", "LegacyStart.cmd"])
    case("alias without consumer proof fails closed", not bool(bad_alias.get("passed")), bad_alias)

    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    managed_paths = {str(item.get("path") or "") for item in manifest.get("files", []) if isinstance(item, dict)}
    expected_runtime_examples = {
        "config/data_contract.json",
        "config/source_connectors.json",
        "config/automation_catalog.json",
        "config/playbook_catalog.json",
        "config/improvement_catalog.json",
        "db/migrations/001_initial.sql",
        "db/migrations/002_semantic_observability.sql",
        "db/migrations/003_source_adapter_registry.sql",
        "db/migrations/004_closed_loop_intelligence.sql",
        "tools/serve_demo.py",
        "tools/operational_store.py",
        "tools/platform_api.py",
        "tools/source_connectors.py",
    }
    scope = {
        "declared_roots": manifest.get("managed_roots"),
        "declared_runtime_files": manifest.get("managed_runtime_files"),
        "missing_examples": sorted(expected_runtime_examples - managed_paths),
    }
    case(
        "governed runtime configs migrations and server modules are fail-closed managed files",
        tuple(manifest.get("managed_roots") or []) == EXPECTED_MANAGED_ROOTS
        and tuple(manifest.get("managed_runtime_files") or []) == EXPECTED_MANAGED_RUNTIME_FILES
        and not scope["missing_examples"],
        scope,
    )

    failed = [item for item in cases if not item["passed"]]
    payload = {
        "schema_version": 1,
        "project": metadata.get("display_name"),
        "version": metadata.get("version"),
        "build": metadata.get("build"),
        "passed": not failed,
        "test_count": len(cases),
        "passed_count": len(cases) - len(failed),
        "failed_count": len(failed),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": cases,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_name(f".{REPORT.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(REPORT)
    print(f"{payload['passed_count']}/{payload['test_count']} launcher-contract checks passed.")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
