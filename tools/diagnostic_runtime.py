#!/usr/bin/env python3
"""Low-overhead, bounded critical diagnostic capture for local application tools."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "diagnostics"
EXPORTS = ROOT / "exports"
STATE_PATH = DIAGNOSTICS / "diagnostic_state.json"
LATEST_CAPSULE = DIAGNOSTICS / "LATEST_CRASH_CAPSULE.txt"
LOG_PATH = DIAGNOSTICS / "server.log"
MAX_LOG_EVENTS = 80
MAX_LOG_FILE_BYTES = 768 * 1024
MAX_TRACE_CHARS = 12_000
MAX_CAPSULES = 12
MAX_CAPSULE_BYTES = 2 * 1024 * 1024
CAPSULE_MAX_AGE_DAYS = 30
EXPORT_TIMEOUT_SECONDS = 9
COOLDOWN_SECONDS = 300

_STATE_LOCK = threading.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else fallback
    except Exception:
        return fallback


def normalize_message(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"(?:[a-z]:\\|/)[^\s:]+", "<path>", text)
    text = re.sub(r"\b\d{2,}\b", "<n>", text)
    text = re.sub(r"\s+", " ", text)
    return text[:1200]


def safe_text(value: Any, limit: int = 8000) -> str:
    text = str(value)
    text = re.sub(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+\-/]+=*", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(?:[A-Z]:\\Users\\|/home/|/Users/)[^\\/\s]+", lambda match: "C:\\Users\\[REDACTED-USER]" if match.group(0).lower().startswith(tuple(f"{letter}:\\users\\" for letter in "abcdefghijklmnopqrstuvwxyz")) else match.group(0).rsplit("/", 1)[0] + "/[REDACTED-USER]", text)
    text = re.sub(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", "[REDACTED-MAC]", text)
    text = re.sub(r"\b(?:10\.|127\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)\d{1,3}\.\d{1,3}\b", "[REDACTED-PRIVATE-IP]", text)
    return text[:limit]


def safe_log_text(value: Any, limit: int = 8000) -> str:
    """Redact and flatten C0/C1 controls before writing one event per log line."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f]+", " ", safe_text(value, limit))[:limit]


def safe_wire_log_text(value: Any, limit: int = 8000) -> str:
    """Make untrusted wire/protocol text ASCII-safe for durable diagnostics.

    BaseHTTPRequestHandler decodes malformed request bytes through a Latin-1-like
    path before logging them. Bytes above 0x9f can therefore look like printable
    Unicode even though they are protocol noise. Escape every non-ASCII codepoint
    at this boundary so the log stays one-event-per-line and text-tool safe.
    """
    text = safe_log_text(value, limit)
    return text.encode("ascii", errors="backslashreplace").decode("ascii")[:limit]


class RingLogger:
    """Bounded recent log buffer plus capped project-local text log."""

    def __init__(self, run_id: str, component: str) -> None:
        self.run_id = run_id
        self.component = component
        self.events: deque[dict[str, str]] = deque(maxlen=MAX_LOG_EVENTS)
        self._lock = threading.Lock()
        DIAGNOSTICS.mkdir(parents=True, exist_ok=True)

    def log(self, severity: str, message: str, details: str = "") -> None:
        event = {
            "timestamp": utc_now().isoformat(),
            "run_id": self.run_id,
            "component": self.component,
            "severity": severity.upper(),
            "message": safe_log_text(message, 1600),
            "details": safe_log_text(details, 3200),
        }
        with self._lock:
            self.events.append(event)
            try:
                if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOG_FILE_BYTES:
                    rotated = LOG_PATH.with_suffix(".log.1")
                    rotated.unlink(missing_ok=True)
                    os.replace(LOG_PATH, rotated)
                line = " | ".join([event["timestamp"], event["run_id"], event["component"], event["severity"], event["message"], event["details"]]).rstrip(" |")
                with LOG_PATH.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                # Diagnostics are best effort and must never destabilize the app.
                pass

    def tail(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self.events)


class DiagnosticRuntime:
    """Create atomic crash capsules and one isolated Export20 per failure storm."""

    def __init__(
        self,
        *,
        run_id: str,
        component: str,
        version: str,
        build: str,
        active_mode: str,
        identity_result: dict[str, Any] | None = None,
        logger: RingLogger | None = None,
    ) -> None:
        self.run_id = run_id
        self.component = component
        self.version = version
        self.build = build
        self.active_mode = active_mode
        self.identity_result = identity_result or {"status": "unknown"}
        self.logger = logger or RingLogger(run_id, component)
        self.last_progress = "Diagnostics initialized"
        self.started_monotonic = time.monotonic()
        self.started_at = utc_now()
        self._capture_lock = threading.Lock()

    def progress(self, message: str) -> None:
        self.last_progress = safe_text(message, 1000)
        self.logger.log("INFO", message)

    def _error_parts(self, error: Any) -> tuple[str, str, str, str]:
        if isinstance(error, BaseException):
            error_class = type(error).__name__
            message = str(error)
            trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        elif isinstance(error, dict):
            error_class = str(error.get("name") or error.get("class") or "ReportedCritical")
            message = str(error.get("message") or error.get("error") or "Terminal critical condition")
            trace = str(error.get("stack") or error.get("trace") or "")
        else:
            error_class = type(error).__name__ if error is not None else "CriticalCondition"
            message = str(error or "Terminal critical condition")
            trace = ""
        top_stack = next((line.strip() for line in trace.splitlines() if line.strip()), "")
        return safe_text(error_class, 180), safe_text(message, 2400), safe_text(trace, MAX_TRACE_CHARS), safe_text(top_stack, 500)

    def _fingerprint(self, error_class: str, message: str, top_stack: str, trigger: str) -> str:
        material = "|".join([
            self.version,
            self.build,
            self.component,
            trigger,
            normalize_message(error_class),
            normalize_message(message),
            normalize_message(top_stack),
        ])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _load_state(self) -> dict[str, Any]:
        state = read_json(STATE_PATH, {})
        if not state:
            state = {"schema_version": 2, "fingerprints": {}, "suppression_total": 0}
        state.setdefault("schema_version", 2)
        state.setdefault("fingerprints", {})
        state.setdefault("suppression_total", 0)
        return state

    def _decide_export(self, fingerprint: str, now: datetime) -> tuple[bool, int, str]:
        with _STATE_LOCK:
            state = self._load_state()
            fingerprints = state["fingerprints"]
            entry = fingerprints.get(fingerprint, {}) if isinstance(fingerprints, dict) else {}
            prior_run = str(entry.get("last_export_run_id") or "")
            prior_at_raw = entry.get("last_export_at")
            prior_at: datetime | None = None
            if isinstance(prior_at_raw, str):
                try:
                    prior_at = datetime.fromisoformat(prior_at_raw)
                except ValueError:
                    prior_at = None
            same_run = prior_run == self.run_id
            cooldown = prior_at is not None and (now - prior_at).total_seconds() < COOLDOWN_SECONDS
            suppression_count = int(entry.get("suppression_count") or 0)
            should_export = not same_run and not cooldown
            reason = "allowed"
            if not should_export:
                suppression_count += 1
                state["suppression_total"] = int(state.get("suppression_total") or 0) + 1
                reason = "same-run fingerprint" if same_run else "cooldown window"
            entry.update({
                "first_seen_at": entry.get("first_seen_at") or now.isoformat(),
                "last_seen_at": now.isoformat(),
                "last_seen_run_id": self.run_id,
                "suppression_count": suppression_count,
                "version": self.version,
                "build": self.build,
            })
            if should_export:
                entry["last_export_at"] = now.isoformat()
                entry["last_export_run_id"] = self.run_id
            fingerprints[fingerprint] = entry
            state["fingerprints"] = fingerprints
            state["last_updated_at"] = now.isoformat()
            atomic_write_json(STATE_PATH, state)
            return should_export, suppression_count, reason

    def _write_capsule(self, payload: dict[str, Any], fingerprint: str, now: datetime) -> Path:
        DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        path = DIAGNOSTICS / f"crash_capsule_{timestamp}_{self.run_id[:24]}_{fingerprint[:10]}.json"
        atomic_write_json(path, payload)
        atomic_write_text(LATEST_CAPSULE, path.relative_to(ROOT).as_posix() + "\n")
        return path

    def _update_capsule(self, path: Path, updates: dict[str, Any]) -> None:
        payload = read_json(path, {})
        payload.update(updates)
        atomic_write_json(path, payload)

    def _run_export(self, *, trigger: str, fingerprint: str, capsule: Path) -> dict[str, Any]:
        started = time.monotonic()
        command = [
            sys.executable,
            str(ROOT / "tools" / "create_support_export.py"),
            "--automatic",
            "--trigger",
            trigger,
            "--run-id",
            self.run_id,
            "--fingerprint",
            fingerprint,
            "--capsule",
            str(capsule),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=EXPORT_TIMEOUT_SECONDS,
                check=False,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            stdout_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if result.returncode == 0 and len(stdout_lines) >= 2:
                export_path = Path(stdout_lines[0])
                return {
                    "status": "completed",
                    "path": export_path.relative_to(ROOT).as_posix() if export_path.is_absolute() else str(export_path),
                    "sha256": stdout_lines[1],
                    "entry_count": int(stdout_lines[2]) if len(stdout_lines) > 2 and stdout_lines[2].isdigit() else None,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            return {
                "status": "failed",
                "reason": safe_text(result.stderr or result.stdout or f"exit {result.returncode}", 1800),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        except subprocess.TimeoutExpired:
            return {"status": "timed-out", "reason": f"Exporter exceeded {EXPORT_TIMEOUT_SECONDS} seconds.", "elapsed_seconds": round(time.monotonic() - started, 3)}
        except Exception as exc:
            return {"status": "failed", "reason": f"{type(exc).__name__}: {safe_text(exc, 1200)}", "elapsed_seconds": round(time.monotonic() - started, 3)}

    def _enforce_capsule_retention(self) -> None:
        files = sorted(DIAGNOSTICS.glob("crash_capsule_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not files:
            return
        cutoff = utc_now() - timedelta(days=CAPSULE_MAX_AGE_DAYS)
        newest = files[0]
        groups: dict[tuple[str, str], list[Path]] = {}
        payloads: dict[Path, dict[str, Any]] = {}
        for path in files:
            payload = read_json(path, {})
            payloads[path] = payload
            key = (str(payload.get("fingerprint") or "unknown"), str(payload.get("version") or "unknown"))
            groups.setdefault(key, []).append(path)
        protected: set[Path] = {newest}
        recent_groups = sorted(groups.values(), key=lambda values: max(item.stat().st_mtime for item in values), reverse=True)[:5]
        for values in recent_groups:
            protected.add(min(values, key=lambda item: item.stat().st_mtime))
            protected.add(max(values, key=lambda item: item.stat().st_mtime))

        kept: list[Path] = []
        total = 0
        for path in files:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            size = path.stat().st_size
            must_keep = path in protected
            fits = len(kept) < MAX_CAPSULES and total + size <= MAX_CAPSULE_BYTES
            if must_keep or (modified >= cutoff and fits):
                kept.append(path)
                total += size
        keep_set = set(kept[:MAX_CAPSULES])
        keep_set.add(newest)
        for path in files:
            if path not in keep_set:
                path.unlink(missing_ok=True)

    def capture_critical(
        self,
        *,
        trigger: str,
        error: Any,
        intended_recovery: str,
        safety_containment: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Capture one terminal Critical event. This method never raises."""
        with self._capture_lock:
            capture_started = time.monotonic()
            now = utc_now()
            try:
                error_class, message, trace, top_stack = self._error_parts(error)
                fingerprint = self._fingerprint(error_class, message, top_stack, trigger)
                should_export, suppression_count, suppression_reason = self._decide_export(fingerprint, now)
                payload: dict[str, Any] = {
                    "schema_version": 2,
                    "project": "Operations Intelligence & Automation Platform",
                    "canonical_project": "Professional Portfolio — Operations Intelligence & Automation Platform",
                    "showcase_module": "Service Operations Command Center",
                    "run_id": self.run_id,
                    "version": self.version,
                    "build": self.build,
                    "component": self.component,
                    "active_mode": self.active_mode,
                    "trigger": safe_text(trigger, 300),
                    "severity": "Critical",
                    "fingerprint": fingerprint,
                    "timestamp": now.isoformat(),
                    "last_progress": self.last_progress,
                    "elapsed_since_start_seconds": round(time.monotonic() - self.started_monotonic, 3),
                    "error": {"class": error_class, "message": message, "top_stack": top_stack, "trace": trace},
                    "recent_log": self.logger.tail(),
                    "runtime_identity_result": self.identity_result,
                    "safety_containment": safe_text(safety_containment, 1600),
                    "intended_recovery": safe_text(intended_recovery, 1600),
                    "suppression_count": suppression_count,
                    "exporter": {"status": "pending" if should_export else "suppressed", "reason": suppression_reason if not should_export else "allowed"},
                    "rights": "Copyright © 2026 Gateway Information Group LLC. All rights reserved.",
                }
                if extra:
                    payload["context"] = json.loads(json.dumps(extra, default=str))
                capsule = self._write_capsule(payload, fingerprint, now)
                self.logger.log("CRITICAL", f"Critical diagnostic trigger: {trigger}", f"fingerprint={fingerprint[:12]} capsule={capsule.name}")
                exporter = self._run_export(trigger=trigger, fingerprint=fingerprint, capsule=capsule) if should_export else payload["exporter"]
                self._update_capsule(capsule, {
                    "exporter": exporter,
                    "capture_elapsed_seconds": round(time.monotonic() - capture_started, 3),
                })
                self._enforce_capsule_retention()
                return {"capsule": capsule, "fingerprint": fingerprint, "exporter": exporter, "suppression_count": suppression_count}
            except Exception as exc:
                # Minimal fallback; never invoke the exporter recursively from here.
                fallback = DIAGNOSTICS / "crash_capsule_fallback.json"
                try:
                    atomic_write_json(fallback, {
                        "schema_version": 1,
                        "project": "Operations Intelligence & Automation Platform",
                        "run_id": self.run_id,
                        "trigger": safe_text(trigger, 300),
                        "timestamp": now.isoformat(),
                        "capture_failure": f"{type(exc).__name__}: {safe_text(exc, 1800)}",
                        "original_error": safe_text(error, 2400),
                        "exporter": {"status": "not-attempted", "reason": "capsule capture failed"},
                    })
                    atomic_write_text(LATEST_CAPSULE, fallback.relative_to(ROOT).as_posix() + "\n")
                except Exception:
                    pass
                return {"capsule": fallback, "fingerprint": "fallback", "exporter": {"status": "not-attempted"}, "suppression_count": 0}
