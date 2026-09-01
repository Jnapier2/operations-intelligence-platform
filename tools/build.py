#!/usr/bin/env python3
"""Build a clean static production bundle and its managed-file manifest."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PUBLIC = ROOT / "public"
GENERATED_RELEASE_TS = ROOT / "src" / "release.generated.ts"
MANAGED_RUNTIME_ROOTS = ("dist", "netlify/functions", "config", "db/migrations")
MANAGED_RUNTIME_FILES = (
    "tools/serve_demo.py",
    "tools/operational_store.py",
    "tools/platform_api.py",
    "tools/source_connectors.py",
    "tools/diagnostic_runtime.py",
    "tools/create_support_export.py",
)


def run(command: list[str]) -> None:
    if os.name == "nt" and Path(command[0]).suffix.lower() in {".cmd", ".bat"}:
        command_shell = os.environ.get("ComSpec") or shutil.which("cmd.exe")
        if not command_shell:
            raise RuntimeError("Windows command shell is unavailable for the build tool shim.")
        command_line = subprocess.list2cmdline(command)
        subprocess.run(
            command_line,
            cwd=ROOT,
            check=True,
            shell=True,
            executable=command_shell,
        )
        return
    subprocess.run(command, cwd=ROOT, check=True)


def typescript_command() -> list[str]:
    """Return a directly executable TypeScript compiler command."""
    node_override = os.environ.get("OIAP_NODE_EXE", "").strip()
    compiler_override = os.environ.get("OIAP_TSC_JS", "").strip()
    if node_override or compiler_override:
        if not node_override or not compiler_override:
            raise RuntimeError("OIAP_NODE_EXE and OIAP_TSC_JS must be provided together.")
        if not Path(node_override).is_file() or not Path(compiler_override).is_file():
            raise RuntimeError("The configured TypeScript compiler override is unavailable.")
        return [node_override, compiler_override]

    compiler = shutil.which("tsc")
    if not compiler:
        raise RuntimeError(
            "TypeScript compiler not found. Install the locked build tool or set "
            "OIAP_NODE_EXE and OIAP_TSC_JS."
        )
    return [compiler]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_identity() -> tuple[str, dict[str, Any]]:
    version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
    metadata = json.loads((ROOT / "PACKAGE_METADATA.json").read_text(encoding="utf-8"))
    if str(metadata.get("version") or "") != version:
        raise RuntimeError("VERSION.txt and PACKAGE_METADATA.json do not agree.")
    if not metadata.get("build"):
        raise RuntimeError("PACKAGE_METADATA.json has no build identity.")
    return version, metadata


def write_generated_release(version: str, build: str) -> None:
    GENERATED_RELEASE_TS.write_text(
        "// Generated from VERSION.txt and PACKAGE_METADATA.json by tools/build.py.\n"
        f"export const APP_VERSION = {json.dumps(version)};\n"
        f"export const APP_BUILD = {json.dumps(build)};\n",
        encoding="utf-8",
    )


def copy_public() -> None:
    for source in PUBLIC.rglob("*"):
        if source.is_dir():
            continue
        relative = source.relative_to(PUBLIC)
        target = DIST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def copy_runtime_catalogs() -> None:
    target = DIST / "data"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("automation_catalog.json", "playbook_catalog.json", "improvement_catalog.json"):
        shutil.copy2(ROOT / "config" / name, target / name)


def write_runtime_identity(version: str, metadata: dict[str, Any]) -> None:
    payload = {
        "schema_version": 1,
        "project": metadata.get("display_name"),
        "showcase_module": metadata.get("showcase_module"),
        "version": version,
        "build": metadata.get("build"),
        "package_id": metadata.get("package_id"),
        "publisher": metadata.get("publisher"),
        "release_channel": metadata.get("release_channel"),
        "copyright": metadata.get("copyright"),
    }
    (DIST / "release.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_manifest(version: str, metadata: dict[str, Any]) -> None:
    managed_paths: list[Path] = []
    for relative_root in MANAGED_RUNTIME_ROOTS:
        root = ROOT / relative_root
        managed_paths.extend(path for path in root.rglob("*") if path.is_file())
    managed_paths.extend(ROOT / relative for relative in MANAGED_RUNTIME_FILES)
    managed_paths = sorted(set(managed_paths))
    files = []
    for path in sorted(managed_paths):
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
    manifest = {
        "schema_version": 2,
        "project": metadata.get("display_name"),
        "package_id": metadata.get("package_id"),
        "version": version,
        "build": metadata.get("build"),
        "release_channel": metadata.get("release_channel"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "managed_roots": list(MANAGED_RUNTIME_ROOTS),
        "managed_runtime_files": list(MANAGED_RUNTIME_FILES),
        "managed_file_count": len(files),
        "control_file_sha256": {
            "VERSION.txt": sha256(ROOT / "VERSION.txt"),
            "PACKAGE_METADATA.json": sha256(ROOT / "PACKAGE_METADATA.json"),
            "SBOM.json": sha256(ROOT / "SBOM.json"),
            "netlify.toml": sha256(ROOT / "netlify.toml"),
            "OperationsIntelligence.bat": sha256(ROOT / "OperationsIntelligence.bat"),
            "tools/verify_release.py": sha256(ROOT / "tools" / "verify_release.py"),
        },
        "files": files,
        "rights": metadata.get("copyright"),
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    version, metadata = load_identity()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)
    write_generated_release(version, str(metadata["build"]))
    run([*typescript_command(), "--project", "tsconfig.json", "--pretty", "false"])
    copy_public()
    copy_runtime_catalogs()
    write_runtime_identity(version, metadata)
    build_manifest(version, metadata)
    print(f"Built production bundle v{version} / {metadata['build']} in {DIST}")


if __name__ == "__main__":
    main()
