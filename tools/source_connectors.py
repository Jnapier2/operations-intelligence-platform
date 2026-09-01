#!/usr/bin/env python3
"""Bounded source-adapter registry for governed ingestion.

The release ships only a project-local CSV adapter. It performs no network
activity and gives future approved source adapters one explicit integration
boundary instead of allowing ingestion logic to proliferate across the app.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "source_connectors.json"
DEFAULT_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class SourceSnapshot:
    connector_id: str
    dataset_name: str
    source_name: str
    csv_text: str
    content_sha256: str
    byte_count: int


def load_registry() -> dict[str, dict[str, Any]]:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    if int(payload.get("schema_version") or 0) != 1:
        raise RuntimeError("Unsupported source connector registry version.")
    registry: dict[str, dict[str, Any]] = {}
    for raw in payload.get("connectors", []):
        if not isinstance(raw, dict):
            raise RuntimeError("Source connector definitions must be objects.")
        connector_id = str(raw.get("id") or "").strip()
        if not connector_id or connector_id in registry:
            raise RuntimeError("Source connector IDs must be non-empty and unique.")
        registry[connector_id] = raw
    return registry


def read_snapshot(connector_id: str) -> SourceSnapshot:
    definition = load_registry().get(connector_id)
    if definition is None:
        raise KeyError(f"Unknown source connector: {connector_id}")
    if not bool(definition.get("enabled")):
        raise RuntimeError(f"Source connector is disabled: {connector_id}")
    connector_type = str(definition.get("type") or "")
    if connector_type != "local_csv":
        raise RuntimeError(f"Unsupported source connector type in this release: {connector_type}")

    relative = Path(str(definition.get("path") or ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError("Local source connector path must be project-root-relative and traversal-free.")
    root = ROOT.resolve()
    source = (ROOT / relative).resolve()
    if source != root and root not in source.parents:
        raise RuntimeError("Local source connector resolved outside the project root.")
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("Local source connector must resolve to a regular project file.")

    max_bytes = int(definition.get("max_bytes") or DEFAULT_MAX_BYTES)
    if max_bytes < 1 or max_bytes > DEFAULT_MAX_BYTES:
        raise RuntimeError("Local source connector max_bytes exceeds the release safety bound.")
    raw = source.read_bytes()
    if len(raw) > max_bytes:
        raise RuntimeError("Local source connector exceeded its configured byte limit.")
    text = raw.decode("utf-8-sig")
    return SourceSnapshot(
        connector_id=connector_id,
        dataset_name=str(definition.get("dataset_name") or connector_id)[:180],
        source_name=str(definition.get("source_name") or connector_id)[:180],
        csv_text=text,
        content_sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )
