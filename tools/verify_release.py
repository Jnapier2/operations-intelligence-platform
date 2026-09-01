#!/usr/bin/env python3
"""Fail-closed release identity and managed-file verification."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "verification_report.json"
REQUIRED = ["VERSION.txt", "PACKAGE_METADATA.json", "MANIFEST.json", "SBOM.json", "dist/release.json", "netlify.toml", "netlify/functions/summary.mjs", "OperationsIntelligence.bat"]
EXPECTED_BASELINE_NAME = "Gateway shared project defaults v2.17.13"
EXPECTED_BASELINE_SHA256 = "63BDA0B5F61BA44F18F55C5B75512085ED3A2FE67C575E3406A5877ECD5F4566"
LAUNCHER_EXCLUDED_PARTS = {".git", "archive", "backups", "cache", "diagnostics", "downloads", "exports", "state", "temp"}
EXPECTED_MANAGED_ROOTS = ("dist", "netlify/functions", "config", "db/migrations")
EXPECTED_MANAGED_RUNTIME_FILES = (
    "tools/serve_demo.py",
    "tools/operational_store.py",
    "tools/platform_api.py",
    "tools/source_connectors.py",
    "tools/diagnostic_runtime.py",
    "tools/create_support_export.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("root value is not an object")
        return value
    except Exception as exc:
        errors.append(f"Invalid JSON in {path.relative_to(ROOT).as_posix()}: {type(exc).__name__}: {exc}")
        return {}


def write_report(result: dict[str, Any]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_name(f".{REPORT.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, REPORT)


def active_launcher_contract(metadata: dict[str, Any], discovered: list[str] | None = None) -> dict[str, Any]:
    execution = metadata.get("execution") if isinstance(metadata.get("execution"), dict) else {}
    canonical = str(execution.get("canonical_entrypoint") or "")
    approved_raw = execution.get("approved_launcher_files")
    approved = [str(value) for value in approved_raw] if isinstance(approved_raw, list) else []
    aliases_raw = execution.get("approved_aliases")
    aliases = aliases_raw if isinstance(aliases_raw, list) else []
    actions_raw = execution.get("action_registry")
    actions = actions_raw if isinstance(actions_raw, list) else []

    problems: list[str] = []
    approved_folded = [value.casefold() for value in approved]
    if not canonical or canonical.casefold() not in approved_folded:
        problems.append("Canonical entrypoint is missing from approved_launcher_files.")
    if len(approved_folded) != len(set(approved_folded)):
        problems.append("approved_launcher_files contains a case-insensitive duplicate.")

    approved_alias_files: set[str] = set()
    for alias in aliases:
        if not isinstance(alias, dict):
            problems.append("Every approved alias must be a registry object with consumer evidence.")
            continue
        filename = str(alias.get("file") or "")
        consumers = alias.get("consumers")
        if not filename or not isinstance(consumers, list) or not [item for item in consumers if str(item).strip()]:
            problems.append(f"Approved alias lacks consumer evidence: {filename or '(unnamed)'}")
            continue
        approved_alias_files.add(filename.casefold())
        if filename.casefold() not in approved_folded:
            problems.append(f"Approved alias is not listed in approved_launcher_files: {filename}")

    if discovered is None:
        discovered = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".bat", ".cmd"}:
                continue
            relative = path.relative_to(ROOT)
            if any(part.casefold() in LAUNCHER_EXCLUDED_PARTS for part in relative.parts[:-1]):
                continue
            discovered.append(relative.as_posix())
    discovered = sorted(set(discovered), key=str.casefold)
    discovered_folded = [value.casefold() for value in discovered]

    unexpected = [value for value in discovered if value.casefold() not in set(approved_folded)]
    missing = [value for value in approved if value.casefold() not in set(discovered_folded)]
    if unexpected:
        problems.append("Unapproved BAT/CMD launcher(s) found: " + ", ".join(unexpected))
    if missing:
        problems.append("Approved BAT/CMD launcher(s) missing: " + ", ".join(missing))
    if len(discovered_folded) != len(set(discovered_folded)):
        problems.append("Active BAT/CMD paths contain a case-insensitive collision.")

    action_ids: list[str] = []
    for action in actions:
        if not isinstance(action, dict):
            problems.append("Action registry contains a non-object entry.")
            continue
        action_id = str(action.get("id") or "")
        launcher = str(action.get("launcher") or "")
        backend = str(action.get("backend") or "")
        if not action_id or not launcher or not backend:
            problems.append("Action registry entry is missing id, launcher, or backend.")
            continue
        action_ids.append(action_id.casefold())
        if launcher.casefold() not in set(approved_folded):
            problems.append(f"Action {action_id} references an unapproved launcher: {launcher}")
    if len(action_ids) != len(set(action_ids)):
        problems.append("Action registry contains a duplicate action id.")
    if not actions:
        problems.append("Action registry is empty.")

    return {
        "passed": not problems,
        "canonical_entrypoint": canonical,
        "execution_namespace": str(execution.get("namespace") or ""),
        "discovered_launcher_files": discovered,
        "approved_launcher_files": approved,
        "approved_alias_count": len(approved_alias_files),
        "action_count": len(actions),
        "problems": problems,
    }


def verify(*, persist_report: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"Missing required release file: {relative}")
    if errors:
        result = {"passed": False, "errors": errors, "checks": checks, "verified_at": datetime.now(timezone.utc).isoformat()}
        if persist_report:
            write_report(result)
        return result

    version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
    metadata = load_json(ROOT / "PACKAGE_METADATA.json", errors)
    manifest = load_json(ROOT / "MANIFEST.json", errors)
    sbom = load_json(ROOT / "SBOM.json", errors)
    runtime = load_json(ROOT / "dist" / "release.json", errors)

    versions = {
        "VERSION.txt": version,
        "PACKAGE_METADATA.json": str(metadata.get("version") or ""),
        "MANIFEST.json": str(manifest.get("version") or ""),
        "dist/release.json": str(runtime.get("version") or ""),
        "SBOM.json": str(((sbom.get("metadata") or {}).get("component") or {}).get("version") or ""),
    }
    version_ok = bool(version) and len(set(versions.values())) == 1
    checks.append({"name": "version_coherence", "passed": version_ok, "details": versions})
    if not version_ok:
        errors.append(f"Release version mismatch: {versions}")

    builds = {
        "PACKAGE_METADATA.json": str(metadata.get("build") or ""),
        "MANIFEST.json": str(manifest.get("build") or ""),
        "dist/release.json": str(runtime.get("build") or ""),
    }
    build_ok = all(builds.values()) and len(set(builds.values())) == 1
    checks.append({"name": "build_coherence", "passed": build_ok, "details": builds})
    if not build_ok:
        errors.append(f"Release build mismatch: {builds}")

    package_ids = {
        "PACKAGE_METADATA.json": str(metadata.get("package_id") or ""),
        "MANIFEST.json": str(manifest.get("package_id") or ""),
        "dist/release.json": str(runtime.get("package_id") or ""),
    }
    package_ok = all(package_ids.values()) and len(set(package_ids.values())) == 1
    checks.append({"name": "package_identity", "passed": package_ok, "details": package_ids})
    if not package_ok:
        errors.append(f"Package identity mismatch: {package_ids}")

    launcher_result = active_launcher_contract(metadata)
    checks.append({"name": "active_launcher_contract", **launcher_result})
    if not launcher_result["passed"]:
        errors.extend(f"Launcher contract: {problem}" for problem in launcher_result["problems"])

    control_expected = manifest.get("control_file_sha256") if isinstance(manifest.get("control_file_sha256"), dict) else {}
    control_actual = {
        "VERSION.txt": sha256(ROOT / "VERSION.txt"),
        "PACKAGE_METADATA.json": sha256(ROOT / "PACKAGE_METADATA.json"),
        "SBOM.json": sha256(ROOT / "SBOM.json"),
        "netlify.toml": sha256(ROOT / "netlify.toml"),
        "OperationsIntelligence.bat": sha256(ROOT / "OperationsIntelligence.bat"),
        "tools/verify_release.py": sha256(ROOT / "tools" / "verify_release.py"),
    }
    control_ok = all(str(control_expected.get(name) or "").lower() == digest for name, digest in control_actual.items())
    checks.append({"name": "control_file_hashes", "passed": control_ok, "expected": control_expected, "actual": control_actual})
    if not control_ok:
        errors.append("One or more release control-file hashes do not match MANIFEST.json.")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("MANIFEST.json has no managed production files.")
        files = []
    declared_count = manifest.get("managed_file_count")
    count_ok = declared_count == len(files)
    checks.append({"name": "manifest_count", "passed": count_ok, "declared": declared_count, "actual": len(files)})
    if not count_ok:
        errors.append("Manifest managed-file count is inconsistent.")

    seen: set[str] = set()
    seen_casefold: set[str] = set()
    verified_count = 0
    mismatch_paths: list[str] = []
    declared_roots = tuple(str(item) for item in (manifest.get("managed_roots") or []))
    declared_runtime_files = tuple(str(item) for item in (manifest.get("managed_runtime_files") or []))
    scope_ok = declared_roots == EXPECTED_MANAGED_ROOTS and declared_runtime_files == EXPECTED_MANAGED_RUNTIME_FILES
    checks.append({
        "name": "managed_scope_contract",
        "passed": scope_ok,
        "managed_roots": list(declared_roots),
        "managed_runtime_files": list(declared_runtime_files),
    })
    if not scope_ok:
        errors.append("Manifest runtime-managed scope does not match the verifier's governed runtime contract.")

    actual_managed_tree = {
        path.relative_to(ROOT).as_posix()
        for relative_root in EXPECTED_MANAGED_ROOTS
        for path in (ROOT / relative_root).rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    actual_managed_tree.update(EXPECTED_MANAGED_RUNTIME_FILES)
    for entry in files:
        if not isinstance(entry, dict):
            errors.append("Manifest contains a non-object file entry.")
            continue
        relative = str(entry.get("path") or "")
        normalized = Path(relative)
        safe = (
            relative in actual_managed_tree
            and "\\" not in relative
            and not normalized.is_absolute()
            and ".." not in normalized.parts
            and relative not in seen
            and relative.casefold() not in seen_casefold
        )
        seen.add(relative)
        seen_casefold.add(relative.casefold())
        if not safe:
            errors.append(f"Unsafe or duplicate manifest path: {relative}")
            mismatch_paths.append(relative)
            continue
        path = ROOT / normalized
        if not path.is_file() or path.is_symlink():
            errors.append(f"Managed file is missing or not a regular file: {relative}")
            mismatch_paths.append(relative)
            continue
        actual_size = path.stat().st_size
        actual_hash = sha256(path)
        if actual_size != entry.get("size"):
            errors.append(f"Size mismatch: {relative}")
            mismatch_paths.append(relative)
            continue
        if actual_hash.lower() != str(entry.get("sha256") or "").lower():
            errors.append(f"SHA-256 mismatch: {relative}")
            mismatch_paths.append(relative)
            continue
        verified_count += 1

    declared_paths = {str(entry.get("path") or "") for entry in files if isinstance(entry, dict)}
    unmanaged = sorted(actual_managed_tree - declared_paths)
    absent = sorted(declared_paths - actual_managed_tree)
    tree_ok = not unmanaged and not absent
    checks.append({"name": "managed_tree_coverage", "passed": tree_ok, "unmanaged": unmanaged, "missing": absent})
    if unmanaged:
        errors.append(f"Unmanaged production files found: {', '.join(unmanaged[:8])}")
    if absent:
        errors.append(f"Manifest files absent from production tree: {', '.join(absent[:8])}")

    managed_ok = verified_count == len(files) and not mismatch_paths
    checks.append({"name": "managed_file_hashes", "passed": managed_ok, "managed": len(files), "verified": verified_count, "mismatch_paths": mismatch_paths})

    baseline_actual = str(metadata.get("source_baseline_sha256") or "").upper()
    baseline_name_actual = str(metadata.get("source_baseline") or "")
    baseline_ok = baseline_actual == EXPECTED_BASELINE_SHA256 and baseline_name_actual == EXPECTED_BASELINE_NAME
    checks.append({
        "name": "source_baseline_receipt",
        "passed": baseline_ok,
        "expected_name": EXPECTED_BASELINE_NAME,
        "actual_name": baseline_name_actual,
        "expected": EXPECTED_BASELINE_SHA256,
        "actual": baseline_actual,
    })
    if not baseline_ok:
        errors.append("Source baseline identity does not match the adopted v2.17.13 parameter package.")

    result = {
        "schema_version": 2,
        "passed": not errors,
        "project": metadata.get("display_name") or "Operations Intelligence & Automation Platform",
        "version": version,
        "build": metadata.get("build"),
        "managed_file_count": len(files),
        "verified_file_count": verified_count,
        "pre_auth_assertion": "No credential or authenticated integration may run unless this report passes.",
        "errors": errors,
        "checks": checks,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    if persist_report:
        write_report(result)
    return result


def main() -> int:
    result = verify()
    if result["passed"]:
        print(f"Release verification PASS — v{result['version']} — {result['build']} — {result['verified_file_count']}/{result['managed_file_count']} files")
        return 0
    print("Release verification FAILED", file=sys.stderr)
    for error in result["errors"]:
        print(f"- {error}", file=sys.stderr)
    try:
        from diagnostic_runtime import DiagnosticRuntime, RingLogger
        run_id = f"verify-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.urandom(3).hex()}"
        logger = RingLogger(run_id, "release-verifier")
        runtime = DiagnosticRuntime(
            run_id=run_id,
            component="release-verifier",
            version=str(result.get("version") or "unknown"),
            build=str(result.get("build") or "unknown"),
            active_mode="release-identity-gate",
            identity_result=result,
            logger=logger,
        )
        runtime.capture_critical(
            trigger="runtime-identity-failure",
            error={"name": "ReleaseIdentityFailure", "message": "; ".join(result["errors"]), "stack": "tools/verify_release.py"},
            safety_containment="Verification failed closed; serving and deployment stopped before credentials or authenticated integrations.",
            intended_recovery="Run tools/build.py, tests/run_tests.mjs, and tools/verify_release.py. Do not bypass the release gate.",
            extra={"verification": result},
        )
    except Exception:
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
