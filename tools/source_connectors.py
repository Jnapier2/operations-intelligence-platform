#!/usr/bin/env python3
"""Bounded source-adapter registry for governed ingestion.

The release ships only a project-local CSV adapter. It performs no network
activity and gives future approved source adapters one explicit integration
boundary instead of allowing ingestion logic to proliferate across the app.

Copyright © 2026 Gateway Information Group LLC. All rights reserved.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "source_connectors.json"
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
MAX_REGISTRY_BYTES = 64 * 1024
MAX_CONNECTORS = 128


@dataclass(frozen=True)
class SourceSnapshot:
    connector_id: str
    dataset_name: str
    source_name: str
    csv_text: str
    content_sha256: str
    byte_count: int


def _project_file(relative: str) -> Path:
    """Check lexical components before resolution can erase link information."""
    if not isinstance(relative, str) or not relative or '\x00' in relative:
        raise RuntimeError("Local source connector path must be non-empty text.")
    windows = PureWindowsPath(relative)
    parts = relative.replace('\\', '/').split('/')
    if windows.drive or windows.root or any(part in ('', '.', '..') for part in parts) or ':' in relative:
        raise RuntimeError("Local source connector path must be project-root-relative and traversal-free.")
    root = ROOT.resolve(strict=True)
    candidate = root
    try:
        for index, part in enumerate(parts):
            candidate = candidate / part
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise RuntimeError("Local source paths may not contain links or reparse points.")
            if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
                raise RuntimeError("Local source parent must be a directory.")
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("Local source connector must resolve to a regular project file.")
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, ValueError):
        raise RuntimeError("Local source path could not be verified inside the project.") from None
    return candidate


def _read_bounded(path: Path, limit: int) -> bytes:
    """Read at most limit + 1 bytes; reject observed replacement or modification.

    Nonblocking/no-follow flags are used where available, but this is not a
    complete hostile-writer filesystem sandbox or an end-to-end time deadline.
    """
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or getattr(before, 'st_file_attributes', 0) & 0x400:
        raise RuntimeError("Local source is not a regular non-linked file.")
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    descriptor = os.open(path, flags)
    try:
        handle = os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise
    with handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
            raise RuntimeError("Local source changed before reading.")
        if opened.st_size > limit:
            raise RuntimeError("Local source exceeded its configured byte limit.")
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if len(raw) > limit:
        raise RuntimeError("Local source exceeded its configured byte limit.")
    if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != after.st_size:
        raise RuntimeError("Local source changed while reading; retry a stable snapshot.")
    return raw


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate registry field")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("Non-finite registry value")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite registry value")
    return number


def load_registry() -> dict[str, dict[str, Any]]:
    try:
        relative = CONFIG.relative_to(ROOT).as_posix()
        raw_bytes = _read_bounded(_project_file(relative), MAX_REGISTRY_BYTES)
        payload = json.loads(raw_bytes.decode('utf-8'), object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant, parse_float=_finite_float)
    except (OSError, ValueError, RecursionError):
        raise RuntimeError("Source connector registry is unavailable or invalid UTF-8 JSON.") from None
    if not isinstance(payload, dict) or type(payload.get('schema_version')) is not int or payload['schema_version'] != 1:
        raise RuntimeError("Unsupported source connector registry version.")
    definitions = payload.get('connectors')
    if not isinstance(definitions, list) or len(definitions) > MAX_CONNECTORS:
        raise RuntimeError("Source connectors must be an array within the registry limit.")
    registry: dict[str, dict[str, Any]] = {}
    for raw in definitions:
        if not isinstance(raw, dict):
            raise RuntimeError("Source connector definitions must be objects.")
        connector_id = raw.get('id')
        if not isinstance(connector_id, str) or not connector_id.strip():
            raise RuntimeError("Source connector IDs must be non-empty strings.")
        connector_id = connector_id.strip()
        if connector_id in registry:
            raise RuntimeError("Source connector IDs must be non-empty and unique.")
        if type(raw.get('enabled', False)) is not bool:
            raise RuntimeError("Source connector enabled must be a JSON boolean.")
        max_bytes = raw.get('max_bytes', DEFAULT_MAX_BYTES)
        if type(max_bytes) is not int or not 1 <= max_bytes <= DEFAULT_MAX_BYTES:
            raise RuntimeError("Local source connector max_bytes must be an integer within the release safety bound.")
        registry[connector_id] = raw
    return registry


def read_snapshot(connector_id: str) -> SourceSnapshot:
    definition = load_registry().get(connector_id)
    if definition is None:
        raise KeyError(f"Unknown source connector: {connector_id}")
    if definition.get('enabled', False) is not True:
        raise RuntimeError(f"Source connector is disabled: {connector_id}")
    connector_type = definition.get('type')
    if connector_type != 'local_csv':
        raise RuntimeError("Unsupported source connector type in this release.")
    source = _project_file(definition.get('path'))
    try:
        raw = _read_bounded(source, definition.get('max_bytes', DEFAULT_MAX_BYTES))
        text = raw.decode('utf-8-sig')
    except (OSError, UnicodeError):
        raise RuntimeError("Local source CSV is unavailable or is not valid UTF-8.") from None
    return SourceSnapshot(
        connector_id=connector_id,
        dataset_name=str(definition.get('dataset_name') or connector_id)[:180],
        source_name=str(definition.get('source_name') or connector_id)[:180],
        csv_text=text,
        content_sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
    )
