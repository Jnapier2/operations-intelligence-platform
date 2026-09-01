#!/usr/bin/env python3
"""Create verified, versioned portfolio and static-deploy archives.

The full archive includes source, documentation, tests, production assets, and
verification evidence. Runtime logs, crash capsules, prior exports, caches, and
temporary files are excluded. A separate static archive contains only `dist`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
INDEX_PATH = ROOT / "PACKAGE_FILE_INDEX.json"
INVENTORY_PATH = REPORTS / "package_inventory_report.json"
ARCHIVE_ROOT = "Operations_Intelligence_Automation_Platform"
FIXED_ZIP_TIME = (2026, 8, 31, 0, 0, 0)
RUNTIME_DIRECTORY_ENTRIES = ("diagnostics", "exports", "temp")
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "cache",
    "diagnostics",
    "downloads",
    "exports",
    "backups",
    "state",
    "temp",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_RUNTIME_FILES = {"reports/field_readiness_report.json"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def safe_source_files(*, include_index: bool) -> list[Path]:
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Symlinks are not allowed in the release package: {path.relative_to(ROOT)}")
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if relative.as_posix() in EXCLUDED_RUNTIME_FILES:
            continue
        if path == INDEX_PATH and not include_index:
            continue
        if path.suffix.lower() == ".zip" or path.name.endswith(".sha256.txt"):
            continue
        files.append(path)
    return files


def classify_duplicate(paths: list[str]) -> str | None:
    if len(paths) == 2:
        left, right = sorted(paths)
        if left.startswith("dist/") and right.startswith("public/") and left.removeprefix("dist/") == right.removeprefix("public/"):
            return "intentional source-to-production boundary"
        if left.startswith("config/") and right.startswith("dist/data/") and left.removeprefix("config/") == right.removeprefix("dist/data/"):
            return "intentional config-to-production boundary"
    return None


def build_inventory(metadata: dict[str, Any]) -> None:
    all_files = [path for path in ROOT.rglob("*") if path.is_file() and not path.is_symlink()]
    package_files = [path for path in safe_source_files(include_index=False) if path != INVENTORY_PATH]
    hashes: dict[str, list[str]] = defaultdict(list)
    for path in package_files:
        hashes[sha256(path)].append(path.relative_to(ROOT).as_posix())

    duplicate_groups = []
    unresolved = []
    for digest, paths in sorted(hashes.items()):
        if len(paths) < 2:
            continue
        classification = classify_duplicate(paths)
        entry = {"sha256": digest, "paths": sorted(paths), "classification": classification or "unresolved"}
        duplicate_groups.append(entry)
        if classification is None:
            unresolved.append(entry)

    excluded = [path for path in all_files if path not in package_files and path not in {INVENTORY_PATH, INDEX_PATH}]
    payload = {
        "schema_version": 1,
        "project": metadata["display_name"],
        "version": metadata["version"],
        "build": metadata["build"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_file_count_before_cleanup": len(all_files),
        "project_bytes_before_cleanup": sum(path.stat().st_size for path in all_files),
        "packaged_source_file_count_before_index": len(package_files),
        "packaged_source_bytes_before_index": sum(path.stat().st_size for path in package_files),
        "excluded_runtime_or_generated_file_count": len(excluded),
        "excluded_runtime_or_generated_bytes": sum(path.stat().st_size for path in excluded),
        "duplicate_groups": duplicate_groups,
        "unresolved_duplicate_groups": unresolved,
        "active_launcher_contract": next(
            (check for check in json.loads((ROOT / "reports" / "verification_report.json").read_text(encoding="utf-8")).get("checks", []) if check.get("name") == "active_launcher_contract"),
            None,
        ) if (ROOT / "reports" / "verification_report.json").is_file() else None,
        "exclusion_policy": sorted(EXCLUDED_PARTS),
        "rights": metadata["copyright"],
    }
    atomic_write_json(INVENTORY_PATH, payload)
    if unresolved:
        details = "; ".join(", ".join(item["paths"]) for item in unresolved)
        raise RuntimeError(f"Unresolved duplicate file content requires review: {details}")


def build_package_index(metadata: dict[str, Any]) -> list[Path]:
    indexed_files = safe_source_files(include_index=False)
    entries = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in indexed_files
    ]
    payload = {
        "schema_version": 1,
        "project": metadata["display_name"],
        "canonical_project_name": metadata["canonical_project_name"],
        "version": metadata["version"],
        "build": metadata["build"],
        "package_id": metadata["package_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "archive_root": ARCHIVE_ROOT,
        "indexed_file_count": len(entries),
        "index_self_excluded": True,
        "runtime_directories_created_empty": list(RUNTIME_DIRECTORY_ENTRIES),
        "files": entries,
        "rights": metadata["copyright"],
    }
    atomic_write_json(INDEX_PATH, payload)
    return safe_source_files(include_index=True)


def zip_info(name: str, *, directory: bool = False) -> zipfile.ZipInfo:
    normalized = name.replace("\\", "/")
    if directory and not normalized.endswith("/"):
        normalized += "/"
    info = zipfile.ZipInfo(normalized, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = ((0o755 if directory else 0o644) << 16) | (0x10 if directory else 0)
    return info


def create_zip_atomic(output: Path, entries: list[tuple[str, Path | None]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            seen: set[str] = set()
            seen_casefold: set[str] = set()
            for arcname, source in entries:
                normalized = arcname.replace("\\", "/")
                path = Path(normalized.rstrip("/"))
                if path.is_absolute() or ".." in path.parts or normalized in seen or normalized.casefold() in seen_casefold:
                    raise RuntimeError(f"Unsafe or duplicate archive path: {normalized}")
                seen.add(normalized)
                seen_casefold.add(normalized.casefold())
                if source is None:
                    archive.writestr(zip_info(normalized, directory=True), b"")
                else:
                    archive.writestr(zip_info(normalized), source.read_bytes())
        with zipfile.ZipFile(temp, "r") as archive:
            failed = archive.testzip()
            if failed:
                raise RuntimeError(f"ZIP integrity failed at {failed}")
            names = archive.namelist()
            if len(names) != len(entries):
                raise RuntimeError("ZIP entry count changed during finalization.")
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)


def verify_full_archive(path: Path, package_files: list[Path]) -> int:
    expected_files = {
        f"{ARCHIVE_ROOT}/{source.relative_to(ROOT).as_posix()}": sha256(source)
        for source in package_files
    }
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        for name, expected in expected_files.items():
            if name not in names:
                raise RuntimeError(f"Packaged file is missing: {name}")
            actual = hashlib.sha256(archive.read(name)).hexdigest()
            if actual != expected:
                raise RuntimeError(f"Packaged file hash mismatch: {name}")
        index = json.loads(archive.read(f"{ARCHIVE_ROOT}/PACKAGE_FILE_INDEX.json"))
        for entry in index["files"]:
            name = f"{ARCHIVE_ROOT}/{entry['path']}"
            actual = hashlib.sha256(archive.read(name)).hexdigest()
            if actual != entry["sha256"]:
                raise RuntimeError(f"Package index mismatch: {entry['path']}")
    return len(names)


def write_receipt(path: Path, archive: Path, metadata: dict[str, Any], entries: int) -> None:
    text = (
        f"SHA256 ({archive.name}) = {sha256(archive)}\n"
        f"Version: {metadata['version']}\n"
        f"Build: {metadata['build']}\n"
        f"Archive entries: {entries}\n"
        "ZIP integrity test: PASS\n"
        f"Copyright: {metadata['copyright']}\n"
    )
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def load_and_verify() -> dict[str, Any]:
    metadata = json.loads((ROOT / "PACKAGE_METADATA.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(ROOT / "tools"))
    from verify_release import verify

    result = verify(persist_report=True)
    if not result.get("passed"):
        raise RuntimeError("Production release verification failed; packaging stopped.")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    metadata = load_and_verify()

    build_inventory(metadata)
    package_files = build_package_index(metadata)
    version = metadata["version"]
    full = output_dir / f"Operations_Intelligence_Automation_Platform_v{version}_Portfolio_Foundation.zip"
    static = output_dir / f"Operations_Intelligence_Automation_Platform_v{version}_Static_Site.zip"

    full_entries: list[tuple[str, Path | None]] = [
        (f"{ARCHIVE_ROOT}/{path.relative_to(ROOT).as_posix()}", path)
        for path in package_files
    ]
    full_entries.extend((f"{ARCHIVE_ROOT}/{directory}/", None) for directory in RUNTIME_DIRECTORY_ENTRIES)
    full_entries.sort(key=lambda item: item[0].casefold())
    create_zip_atomic(full, full_entries)
    full_count = verify_full_archive(full, package_files)
    full_receipt = full.with_suffix(".sha256.txt")
    write_receipt(full_receipt, full, metadata, full_count)

    dist_files = [path for path in sorted((ROOT / "dist").rglob("*")) if path.is_file()]
    static_entries = [(path.relative_to(ROOT / "dist").as_posix(), path) for path in dist_files]
    create_zip_atomic(static, static_entries)
    with zipfile.ZipFile(static, "r") as archive:
        if archive.testzip() is not None or sorted(archive.namelist()) != sorted(name for name, _ in static_entries):
            raise RuntimeError("Static archive verification failed.")
        static_count = len(archive.namelist())
    static_receipt = static.with_suffix(".sha256.txt")
    write_receipt(static_receipt, static, metadata, static_count)

    print(json.dumps({
        "passed": True,
        "full_archive": str(full),
        "full_sha256": sha256(full),
        "full_entries": full_count,
        "static_archive": str(static),
        "static_sha256": sha256(static),
        "static_entries": static_count,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
