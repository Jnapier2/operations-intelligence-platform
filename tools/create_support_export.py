#!/usr/bin/env python3
"""Create a bounded, redacted, project-local Export20 support archive.

The exporter is intentionally isolated and read-only with respect to application
behavior. It uses a deterministic allowlist, performs no network activity,
stages on the project volume, verifies the archive, then atomically finalizes it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
DIAGNOSTICS = ROOT / "diagnostics"
TEMP = ROOT / "temp"
VERSION_TEXT = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
VERSION_SLUG = VERSION_TEXT.replace(".", "_")
LATEST = EXPORTS / f"Operations_Intelligence_v{VERSION_SLUG}_LATEST_SUPPORT_EXPORT.zip"
LATEST_RECEIPT = EXPORTS / f"Operations_Intelligence_v{VERSION_SLUG}_LATEST_SUPPORT_EXPORT.sha256.txt"
LOCK = DIAGNOSTICS / ".support_export.lock"
MAX_ITEMS = 20
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_ELAPSED_SECONDS = 8.0
LOCK_STALE_SECONDS = 120
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
AUTOMATIC_RETENTION_COUNT = 8
AUTOMATIC_RETENTION_BYTES = 48 * 1024 * 1024
AUTOMATIC_RETENTION_DAYS = 30

ALLOWLIST = [
    "VERSION.txt",
    "PACKAGE_METADATA.json",
    "MANIFEST.json",
    "SBOM.json",
    "reports/verification_report.json",
    "reports/field_readiness_report.json",
    "reports/package_inventory_report.json",
    "reports/test_report.json",
    "reports/platform_foundation_test_report.json",
    "reports/http_smoke_report.json",
    "reports/release_contract_test_report.json",
    "reports/browser_smoke_report.json",
    "state/latest_startup_status.json",
    "diagnostics/LATEST_CRASH_CAPSULE.txt",
    "diagnostics/diagnostic_state.json",
    "CHANGELOG.md",
    "KNOWN_GOOD_STATE.md",
    "BUILD_LEDGER.md",
    "docs/ARCHITECTURE.md",
]

TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".log", ".toml"}
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|private[_-]?key)\s*[:=]\s*([^\s,;\"']+)"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+\-/]+=*"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b"), "[REDACTED-MAC]"),
    (re.compile(r"\b(?:10\.|127\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)\d{1,3}\.\d{1,3}\b"), "[REDACTED-PRIVATE-IP]"),
    (re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"), "[REDACTED-UUID]"),
]
USER_PATH_PATTERN = re.compile(r"(?i)(?:[A-Z]:\\Users\\|/home/|/Users/)[^\\/\s]+")


def redact_text(text: str) -> str:
    output = text.replace("\r\n", "\n").replace("\r", "\n")
    for pattern, replacement in SECRET_PATTERNS:
        output = pattern.sub(replacement, output)
    output = USER_PATH_PATTERN.sub(lambda match: match.group(0).rsplit("/", 1)[0] + "/[REDACTED-USER]" if "/" in match.group(0) else "C:\\Users\\[REDACTED-USER]", output)
    # Preserve ordinary line structure while removing binary/control noise from historical logs.
    output = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", " ", output)
    return output




def redact_log_text(text: str) -> str:
    """Redact a log and escape non-ASCII wire noise for portable evidence."""
    output = redact_text(text)
    return output.encode("ascii", errors="backslashreplace").decode("ascii")

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def acquire_lock() -> int:
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - LOCK.stat().st_mtime if LOCK.exists() else 0
        if age <= LOCK_STALE_SECONDS:
            raise RuntimeError("A support export is already active on this computer.")
        LOCK.unlink(missing_ok=True)
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, f"pid={os.getpid()} started={datetime.now(timezone.utc).isoformat()}\n".encode("utf-8"))
    return fd


def release_lock(fd: int) -> None:
    try:
        os.close(fd)
    finally:
        LOCK.unlink(missing_ok=True)


def safe_project_file(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def candidate_items(capsule: str | None) -> list[Path]:
    items: list[Path] = []
    exact_capsule = safe_project_file(capsule)
    if exact_capsule is not None:
        items.append(exact_capsule)
    for relative in ALLOWLIST:
        path = ROOT / relative
        if path.is_file() and path not in items:
            items.append(path)
    # One context item is always generated inside the archive.
    return items[: MAX_ITEMS - 2]


def stable_read(path: Path, deadline: float) -> bytes:
    last_error: Exception | None = None
    for _ in range(2):
        if time.monotonic() > deadline:
            raise TimeoutError("Support-export collection budget expired.")
        try:
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            if before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns:
                return data
        except OSError as exc:
            last_error = exc
        time.sleep(0.04)
    if last_error:
        raise last_error
    raise RuntimeError(f"File changed while being collected: {path.name}")


def current_run_log(deadline: float, requested_run_id: str) -> tuple[str, bytes] | None:
    log_path = DIAGNOSTICS / "server.log"
    if not log_path.is_file():
        return None
    preferred = requested_run_id if requested_run_id and requested_run_id != "manual" else ""
    if not preferred:
        startup = ROOT / "state" / "latest_startup_status.json"
        try:
            payload = json.loads(stable_read(startup, deadline).decode("utf-8")) if startup.is_file() else {}
            preferred = str(payload.get("run_id") or "")
        except Exception:
            preferred = ""
    text = redact_log_text(stable_read(log_path, deadline).decode("utf-8", errors="replace"))
    lines = [line for line in text.splitlines() if line.strip()]
    if not preferred:
        for line in reversed(lines):
            parts = [part.strip() for part in line.split(" | ")]
            if len(parts) >= 2 and parts[1].startswith("local-"):
                preferred = parts[1]
                break
    selected = [line for line in lines if preferred and f" | {preferred} | " in line]
    if not selected:
        selected = lines[-80:]
        preferred = preferred or "latest-available"
    data = ("\n".join(selected[-80:]) + "\n").encode("utf-8")
    return preferred, data


def add_bytes(archive: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, data)


def read_export_context(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            return json.loads(archive.read("SUPPORT_EXPORT_CONTEXT.json").decode("utf-8"))
    except Exception:
        return {}


def enforce_retention() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=AUTOMATIC_RETENTION_DAYS)
    archives = [
        path
        for path in EXPORTS.glob(f"Operations_Intelligence_v{VERSION_SLUG}_*_SUPPORT_EXPORT20.zip")
        if path.is_file()
    ]
    if not archives:
        return
    archives.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    contexts = {path: read_export_context(path) for path in archives}
    newest = archives[0]
    groups: dict[str, list[Path]] = {}
    for path in archives:
        fingerprint = str(contexts[path].get("fingerprint") or "unknown")
        groups.setdefault(fingerprint, []).append(path)

    protected: set[Path] = {newest}
    # Preserve the first useful archive for the five most recently active fingerprints.
    recent_groups = sorted(groups.values(), key=lambda values: max(item.stat().st_mtime for item in values), reverse=True)[:5]
    for values in recent_groups:
        protected.add(min(values, key=lambda item: item.stat().st_mtime))

    keep: list[Path] = []
    total = 0
    for path in archives:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        must_keep = path in protected
        fits = len(keep) < AUTOMATIC_RETENTION_COUNT and total + path.stat().st_size <= AUTOMATIC_RETENTION_BYTES
        recent = modified >= cutoff
        if must_keep or (recent and fits):
            keep.append(path)
            total += path.stat().st_size

    keep_set = set(keep[:AUTOMATIC_RETENTION_COUNT])
    if newest not in keep_set:
        keep_set.add(newest)
    for path in archives:
        if path in keep_set:
            continue
        path.unlink(missing_ok=True)
        path.with_suffix(".sha256.txt").unlink(missing_ok=True)


def slug(value: str, limit: int = 28) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return (cleaned or "unknown")[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--capsule")
    parser.add_argument("--automatic", action="store_true")
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--fingerprint", default="manual")
    args = parser.parse_args()

    start = time.monotonic()
    deadline = start + MAX_ELAPSED_SECONDS
    EXPORTS.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)
    fd = acquire_lock()
    try:
        items = candidate_items(args.capsule)
        collected: list[tuple[Path, bytes]] = []
        skipped: list[dict[str, str]] = []
        total = 0
        for path in items:
            try:
                raw = stable_read(path, deadline)
                if path.suffix.lower() in TEXT_SUFFIXES:
                    raw = redact_text(raw.decode("utf-8", errors="replace")).encode("utf-8")
                if total + len(raw) > MAX_TOTAL_BYTES:
                    skipped.append({"path": path.relative_to(ROOT).as_posix(), "reason": "size budget"})
                    continue
                collected.append((path, raw))
                total += len(raw)
            except Exception as exc:
                skipped.append({"path": path.relative_to(ROOT).as_posix(), "reason": type(exc).__name__})

        synthesized: list[tuple[str, bytes]] = []
        try:
            latest_log = current_run_log(deadline, args.run_id)
            if latest_log is not None:
                latest_run_id, latest_log_raw = latest_log
                if len(collected) + len(synthesized) < MAX_ITEMS - 1 and total + len(latest_log_raw) <= MAX_TOTAL_BYTES:
                    synthesized.append(("diagnostics/latest_startup_run.log", latest_log_raw))
                    total += len(latest_log_raw)
        except Exception as exc:
            skipped.append({"path": "diagnostics/latest_startup_run.log", "reason": type(exc).__name__})

        metadata = json.loads((ROOT / "PACKAGE_METADATA.json").read_text(encoding="utf-8")) if (ROOT / "PACKAGE_METADATA.json").is_file() else {}
        created = datetime.now(timezone.utc)
        context: dict[str, Any] = {
            "schema_version": 2,
            "asset_id": "OIAP-SUPPORT-EXPORT20",
            "project": "Operations Intelligence & Automation Platform",
            "canonical_project": "Professional Portfolio — Operations Intelligence & Automation Platform",
            "showcase_module": "Service Operations Command Center",
            "version": VERSION_TEXT,
            "build": metadata.get("build", "unknown"),
            "run_id": args.run_id,
            "trigger": args.trigger,
            "severity": "Critical" if args.automatic else "Manual",
            "fingerprint": args.fingerprint,
            "created_at": created.isoformat(),
            "automatic": args.automatic,
            "sensitivity": "support-diagnostic; redacted",
            "tags": ["operations-intelligence", "diagnostics", "export20", "portfolio"],
            "lineage": "Gateway shared project defaults v2.17.13 / source-package DIAGNOSTIC_EXPORT_SPEC.md",
            "rights": "Copyright © 2026 Gateway Information Group LLC. All rights reserved.",
            "parameter_receipt": {
                "status": "applied",
                "source_baseline": metadata.get("source_baseline"),
                "sha256": metadata.get("source_baseline_sha256"),
                "rule_families": [
                    "active_launcher_contract",
                    "critical_export20",
                    "release_identity",
                    "windows_root_relative",
                ],
            },
            "execution": {
                "namespace": ((metadata.get("execution") or {}).get("namespace") if isinstance(metadata.get("execution"), dict) else None),
                "canonical_entrypoint": ((metadata.get("execution") or {}).get("canonical_entrypoint") if isinstance(metadata.get("execution"), dict) else None),
                "approved_alias_count": len(((metadata.get("execution") or {}).get("approved_aliases") or [])) if isinstance(metadata.get("execution"), dict) else 0,
                "action_count": len(((metadata.get("execution") or {}).get("action_registry") or [])) if isinstance(metadata.get("execution"), dict) else 0,
            },
            "item_limit": MAX_ITEMS,
            "size_limit_bytes": MAX_TOTAL_BYTES,
            "source_items": [path.relative_to(ROOT).as_posix() for path, _ in collected] + [name for name, _ in synthesized],
            "skipped": skipped,
            "redaction": "Credential-like values, authorization headers, local usernames, private IPs, MAC addresses, UUIDs, and binary/control noise are removed from text evidence.",
            "network_calls": False,
            "behavior_mutation": False,
        }
        context_raw = (json.dumps(context, indent=2, sort_keys=True) + "\n").encode("utf-8")

        timestamp = created.strftime("%Y%m%dT%H%M%SZ")
        if args.automatic:
            final = EXPORTS / (
                f"Operations_Intelligence_v{VERSION_SLUG}_{timestamp}_{slug(args.run_id)}_"
                f"{slug(args.fingerprint, 12)}_SUPPORT_EXPORT20.zip"
            )
        else:
            final = LATEST
        receipt = final.with_suffix(".sha256.txt")

        with tempfile.NamedTemporaryFile(prefix="support_export_", suffix=".zip", dir=TEMP, delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                add_bytes(archive, "SUPPORT_EXPORT_CONTEXT.json", context_raw)
                for path, raw in collected:
                    add_bytes(archive, path.relative_to(ROOT).as_posix(), raw)
                for arcname, raw in synthesized:
                    add_bytes(archive, arcname, raw)
            with zipfile.ZipFile(temp_path, "r") as archive:
                bad = archive.testzip()
                names = archive.namelist()
                if bad:
                    raise RuntimeError(f"ZIP integrity failed at {bad}.")
                if len(names) > MAX_ITEMS:
                    raise RuntimeError(f"ZIP contains {len(names)} entries; limit is {MAX_ITEMS}.")
                if len(names) != len(set(names)):
                    raise RuntimeError("ZIP contains duplicate paths.")
            if time.monotonic() > deadline:
                raise TimeoutError("Support export exceeded the total collection budget.")
            os.replace(temp_path, final)
            digest = sha256(final)
            receipt_text = (
                f"SHA256  {digest}  {final.name}\n"
                f"Created {context['created_at']}\n"
                f"Trigger {args.trigger}\n"
                f"Run {args.run_id}\n"
                f"Fingerprint {args.fingerprint}\n"
                f"Items {len(names)}\n"
                f"ElapsedSeconds {time.monotonic() - start:.3f}\n"
            )
            atomic_write_text(receipt, receipt_text)

            if args.automatic:
                with tempfile.NamedTemporaryFile(prefix="latest_support_", suffix=".zip", dir=TEMP, delete=False) as latest_handle:
                    latest_temp = Path(latest_handle.name)
                try:
                    shutil.copyfile(final, latest_temp)
                    os.replace(latest_temp, LATEST)
                finally:
                    latest_temp.unlink(missing_ok=True)
                atomic_write_text(LATEST_RECEIPT, receipt_text.replace(final.name, LATEST.name, 1))
                enforce_retention()

            print(final)
            print(digest)
            print(len(names))
            return 0
        finally:
            temp_path.unlink(missing_ok=True)
    finally:
        release_lock(fd)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Support export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
