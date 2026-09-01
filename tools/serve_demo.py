#!/usr/bin/env python3
"""Verify and serve the production portfolio bundle on loopback only."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from diagnostic_runtime import DiagnosticRuntime, RingLogger, atomic_write_json, safe_text, safe_wire_log_text
from operational_store import OperationalStore
from platform_api import ApiResponse, PlatformApi
from verify_release import verify

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
HOST = "127.0.0.1"
DEFAULT_PORT = 4173
MAX_DIAGNOSTIC_BODY = 32_000
MAX_API_BODY = 8 * 1024 * 1024
STARTUP_STATUS = ROOT / "state" / "latest_startup_status.json"
FIELD_READINESS_REPORT = ROOT / "reports" / "field_readiness_report.json"

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("text/csv", ".csv")


def load_identity() -> tuple[str, str]:
    version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() if (ROOT / "VERSION.txt").is_file() else "unknown"
    try:
        metadata = json.loads((ROOT / "PACKAGE_METADATA.json").read_text(encoding="utf-8"))
        build = str(metadata.get("build") or "unknown")
    except Exception:
        build = "unknown"
    return version, build


def make_run_id() -> str:
    return f"local-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.urandom(3).hex()}"


def choose_port(preferred: int) -> int:
    if preferred == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((HOST, 0))
            return int(probe.getsockname()[1])
    for port in range(preferred, preferred + 21):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No loopback port was available from {preferred} through {preferred + 20}.")


def is_loopback(address: str) -> bool:
    return address in {"127.0.0.1", "::1", "localhost"} or address.startswith("127.")


def write_startup_status(run_id: str, version: str, build: str, *, stage: str, status: str, details: dict[str, Any] | None = None) -> None:
    """Persist the latest local startup stage atomically for field diagnosis."""
    payload = {
        "schema_version": 1,
        "project": "Operations Intelligence & Automation Platform",
        "version": version,
        "build": build,
        "run_id": run_id,
        "stage": stage,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    }
    try:
        atomic_write_json(STARTUP_STATUS, payload)
    except OSError:
        # Startup evidence must never make a healthy local launch fail.
        pass


def write_field_readiness(run_id: str, version: str, build: str, *, mode: str, identity_result: dict[str, Any], refresh: dict[str, Any], observation: dict[str, Any], kpi_count: int, health: dict[str, Any] | None = None) -> None:
    payload = {
        "schema_version": 1,
        "project": "Operations Intelligence & Automation Platform",
        "version": version,
        "build": build,
        "run_id": run_id,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": bool(identity_result.get("passed")) and str((health or {}).get("status") or "ready") == "ready",
        "release_identity": {
            "passed": bool(identity_result.get("passed")),
            "verified_files": identity_result.get("verified_file_count"),
            "managed_files": identity_result.get("managed_file_count"),
        },
        "governed_store": {
            "status": "ready",
            "kpi_count": kpi_count,
            "slo_measurement_count": len(observation.get("measurements", [])) if isinstance(observation.get("measurements"), list) else 0,
            "refresh_status": refresh.get("status"),
        },
        "http_health": health,
        "rights": "Copyright © 2026 Gateway Information Group LLC. All rights reserved.",
    }
    try:
        atomic_write_json(FIELD_READINESS_REPORT, payload)
    except OSError:
        pass


def probe_http_health(url: str, version: str, build: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/__health", timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Loopback HTTP readiness probe failed: {safe_text(exc, 500)}") from exc
    if (
        response.status != HTTPStatus.OK
        or payload.get("status") != "ready"
        or payload.get("releaseGate") != "PASS"
        or payload.get("version") != version
        or payload.get("build") != build
    ):
        raise RuntimeError("Loopback HTTP readiness probe returned an unexpected release identity or readiness state.")
    return payload


def handler_factory(runtime: DiagnosticRuntime, identity_result: dict[str, Any], run_id: str, version: str, build: str, platform_api: PlatformApi | None = None):
    api = platform_api or PlatformApi(OperationalStore(), release_passed=bool(identity_result.get("passed")))
    class Handler(BaseHTTPRequestHandler):
        server_version = "OperationsIntelligenceLocal"
        sys_version = ""

        def version_string(self) -> str:
            return self.server_version

        def log_message(self, format_string: str, *args: Any) -> None:
            runtime.logger.log("INFO", "HTTP request", safe_wire_log_text(format_string % args, 3200))

        def _headers(self, status: int, content_type: str, content_length: int | None = None, cache_control: str = "no-store", extra_headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if content_length is not None:
                self.send_header("Content-Length", str(content_length))
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
            )
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()

        def _json(self, status: int, payload: dict[str, Any], extra_headers: dict[str, str] | None = None) -> None:
            body = (json.dumps(payload, separators=(",", ":"), default=str) + "\n").encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(body), extra_headers=extra_headers)
            self.wfile.write(body)
            self.wfile.flush()

        def _api_response(self, response: ApiResponse) -> None:
            self._json(response.status, response.payload, response.headers)

        def _read_body(self, maximum: int) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > maximum:
                return None
            return self.rfile.read(length)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlsplit(self.path)
            api_response = api.handle_get(parsed.path, self.headers)
            if api_response is not None:
                self._api_response(api_response)
                return
            if parsed.path == "/__health":
                self._json(HTTPStatus.OK, {
                    "status": "ready",
                    "project": "Operations Intelligence & Automation Platform",
                    "version": version,
                    "build": build,
                    "runId": run_id,
                    "releaseGate": "PASS" if identity_result.get("passed") else "FAIL",
                    "governedStore": "ready",
                    "apiMode": "server-governed",
                })
                return

            requested = urllib.parse.unquote(parsed.path)
            if requested == "/":
                requested = "/index.html"
            relative = Path(requested.lstrip("/"))
            if relative.is_absolute() or ".." in relative.parts:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid path."})
                return
            target = (DIST / relative).resolve()
            try:
                target.relative_to(DIST.resolve())
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid path."})
                return
            if not target.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            try:
                body = target.read_bytes()
            except OSError as exc:
                runtime.logger.log("ERROR", "Static file read failed", f"{target.name}: {exc}")
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The requested file could not be read."})
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
                content_type += "; charset=utf-8"
            cache = "public, max-age=31536000, immutable" if target.parent.name == "assets" else "no-store"
            self._headers(HTTPStatus.OK, content_type, len(body), cache)
            self.wfile.write(body)
            self.wfile.flush()

        def do_POST(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path.startswith("/api/"):
                body = self._read_body(MAX_API_BODY)
                if body is None:
                    self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "API body is missing or too large."})
                    return
                api_response = api.handle_post(parsed.path, self.headers, body)
                if api_response is not None:
                    self._api_response(api_response)
                    return
            if parsed.path != "/__diagnostics/critical":
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            if not is_loopback(self.client_address[0]):
                self._json(HTTPStatus.FORBIDDEN, {"error": "Loopback access only."})
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Diagnostic requests require application/json."})
                return
            fetch_site = self.headers.get("Sec-Fetch-Site", "").strip().lower()
            if fetch_site and fetch_site not in {"same-origin", "none"}:
                self._json(HTTPStatus.FORBIDDEN, {"error": "Cross-site diagnostic requests are not accepted."})
                return
            origin = self.headers.get("Origin", "").strip()
            host = self.headers.get("Host", "").strip()
            if origin and host and origin not in {f"http://{host}", f"https://{host}"}:
                self._json(HTTPStatus.FORBIDDEN, {"error": "Diagnostic request origin is not allowed."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_DIAGNOSTIC_BODY:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Diagnostic body is missing or too large."})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Diagnostic payload must be an object.")
            except Exception as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": safe_text(exc, 400)})
                return
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {
                "name": "BrowserCritical",
                "message": payload.get("message") or "Uncaught browser error",
                "stack": payload.get("stack") or "",
            }
            result = runtime.capture_critical(
                trigger="uncaught-browser-critical",
                error=error,
                safety_containment="The failing browser operation stopped; the local server performed no repair, network, credential, or live business action.",
                intended_recovery="Reload the application, use the browser diagnostic download if needed, and review the project-local crash capsule before changing source data or workflow state.",
                extra={
                    "browser_context": safe_text(payload.get("context") or "window error", 800),
                    "page": safe_text(payload.get("page") or "/", 300),
                    "browser_recent_log": payload.get("recentLog", [])[-40:] if isinstance(payload.get("recentLog"), list) else [],
                },
            )
            exporter = result.get("exporter") if isinstance(result, dict) else {}
            self._json(HTTPStatus.ACCEPTED, {
                "status": "captured",
                "fingerprint": str(result.get("fingerprint", ""))[:12],
                "suppressionCount": result.get("suppression_count", 0),
                "exportStatus": exporter.get("status") if isinstance(exporter, dict) else "unknown",
            })


        def do_PATCH(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlsplit(self.path)
            body = self._read_body(MAX_API_BODY)
            if body is None:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "API body is missing or too large."})
                return
            api_response = api.handle_patch(parsed.path, self.headers, body)
            if api_response is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
            self._api_response(api_response)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._headers(HTTPStatus.NO_CONTENT, "text/plain", 0)

    return Handler


def run(args: argparse.Namespace) -> int:
    version, build = load_identity()
    run_id = make_run_id()
    logger = RingLogger(run_id, "local-server")
    runtime = DiagnosticRuntime(
        run_id=run_id,
        component="local-server",
        version=version,
        build=build,
        active_mode="loopback-governed-server",
        logger=logger,
    )
    server: ThreadingHTTPServer | None = None
    refresh_stop = threading.Event()
    refresh_thread: threading.Thread | None = None
    write_startup_status(run_id, version, build, stage="starting", status="in_progress")
    try:
        runtime.progress(f"Project root resolved from launcher: {ROOT}")
        identity_result = verify()
        runtime.identity_result = identity_result
        if not identity_result.get("passed"):
            runtime.capture_critical(
                trigger="runtime-identity-failure",
                error={"name": "ReleaseIdentityFailure", "message": "; ".join(identity_result.get("errors", [])), "stack": "release verification"},
                safety_containment="Local serving stopped before the application opened and before any optional credential or authenticated integration could be used.",
                intended_recovery="Rebuild with tools/build.py, rerun tests, then rerun tools/verify_release.py. Do not bypass the manifest gate.",
                extra={"verification": identity_result},
            )
            print("Release verification failed. See reports/verification_report.json and diagnostics/.", file=sys.stderr)
            return 1
        runtime.progress(f"Release identity PASS for v{version} / {build}")
        write_startup_status(run_id, version, build, stage="release_verified", status="in_progress", details={"verified_files": identity_result.get("verified_file_count"), "managed_files": identity_result.get("managed_file_count")})
        store = OperationalStore()
        refresh = store.run_scheduled_refresh(force=False)
        platform_api = PlatformApi(store, release_passed=True)
        runtime.progress(f"Governed SQLite store ready; refresh status: {refresh.get('status')}")
        write_startup_status(run_id, version, build, stage="governed_store_ready", status="in_progress", details={"refresh_status": refresh.get("status")})
        if args.check:
            observation = store.observability(True)
            write_field_readiness(run_id, version, build, mode="doctor", identity_result=identity_result, refresh=refresh, observation=observation, kpi_count=len(store.list_kpis()))
            write_startup_status(run_id, version, build, stage="doctor_passed", status="ready", details={"kpi_count": len(store.list_kpis()), "slo_measurement_count": len(observation.get("measurements", []))})
            print(f"Release verification PASS — v{version} — {build}")
            print(f"Governed store PASS — {len(store.list_kpis())} KPI definitions — {len(observation.get('measurements', []))} SLO measurements")
            return 0
        if args.diagnostic_self_test:
            write_startup_status(run_id, version, build, stage="diagnostic_self_test", status="in_progress")
            result = runtime.capture_critical(
                trigger="diagnostic-self-test",
                error={"name": "DiagnosticSelfTest", "message": "Controlled terminal diagnostic capture verification", "stack": "serve_demo.py diagnostic self-test"},
                safety_containment="No application or external action was started; this is a controlled local verification event.",
                intended_recovery="No recovery is required. Review the generated capsule and Export20 integrity receipt.",
                extra={"controlled_test": True},
            )
            exporter = result.get("exporter") if isinstance(result, dict) else {}
            self_test_passed = isinstance(exporter, dict) and exporter.get("status") in {"completed", "suppressed"}
            write_startup_status(
                run_id,
                version,
                build,
                stage="diagnostic_self_test_complete" if self_test_passed else "diagnostic_self_test_failed",
                status="ready" if self_test_passed else "failed",
                details={
                    "export_status": exporter.get("status") if isinstance(exporter, dict) else "unknown",
                    "suppression_count": result.get("suppression_count", 0) if isinstance(result, dict) else 0,
                },
            )
            print(json.dumps({"status": "diagnostic-self-test-complete", "result": result}, default=str, indent=2))
            return 0 if self_test_passed else 1

        if not DIST.is_dir():
            raise RuntimeError("Production directory is missing. Run python tools/build.py first.")
        port = choose_port(args.port)
        write_startup_status(run_id, version, build, stage="port_selected", status="in_progress", details={"port": port})
        handler = handler_factory(runtime, identity_result, run_id, version, build, platform_api)
        server = ThreadingHTTPServer((HOST, port), handler)
        server.daemon_threads = True
        server.timeout = 3.0
        write_startup_status(run_id, version, build, stage="server_bound", status="in_progress", details={"port": port})

        def refresh_worker() -> None:
            while not refresh_stop.wait(60.0):
                try:
                    result = store.run_scheduled_refresh(force=False)
                    if result.get("status") not in {"not_due", "disabled"}:
                        runtime.logger.log("INFO", "Scheduled governed refresh", json.dumps(result, default=str)[:1200])
                except Exception as exc:
                    runtime.logger.log("WARNING", "Scheduled governed refresh failed", safe_text(exc, 800))

        refresh_thread = threading.Thread(target=refresh_worker, name="governed-refresh", daemon=True)
        refresh_thread.start()
        url = f"http://{HOST}:{port}/"

        # Prove the bound server can answer its own governed health endpoint before opening a browser.
        probe_thread = threading.Thread(target=server.handle_request, name="startup-health-probe", daemon=True)
        probe_thread.start()
        health = probe_http_health(url, version, build)
        probe_thread.join(timeout=3.5)
        if probe_thread.is_alive():
            raise RuntimeError("Loopback HTTP readiness probe did not finish within the startup budget.")
        observation = store.observability(True)
        write_field_readiness(run_id, version, build, mode="launch", identity_result=identity_result, refresh=refresh, observation=observation, kpi_count=len(store.list_kpis()), health=health)
        write_startup_status(run_id, version, build, stage="http_ready", status="ready", details={"port": port, "health_status": health.get("status"), "release_gate": health.get("releaseGate")})
        runtime.progress(f"Ready at {url}")
        print("=" * 62)
        print("Operations Intelligence & Automation Platform")
        print("Service Operations Command Center")
        print("=" * 62)
        print(f"Release: v{version} — {build}")
        print(f"Root:    {ROOT}")
        print(f"URL:     {url}")
        print("Release identity: PASS")
        print("Press Ctrl+C to stop.")
        if not args.no_browser:
            def open_browser() -> None:
                time.sleep(0.35)
                try:
                    webbrowser.open(url, new=2)
                except Exception as exc:
                    logger.log("WARNING", "Browser could not be opened automatically", str(exc))
            threading.Thread(target=open_browser, name="open-browser", daemon=True).start()
        server.serve_forever(poll_interval=0.25)
        return 0
    except KeyboardInterrupt:
        logger.log("INFO", "Normal user-requested shutdown")
        write_startup_status(run_id, version, build, stage="stopped", status="normal", details={"reason": "user_requested"})
        print("\nLocal demo stopped.")
        return 0
    except BaseException as exc:
        write_startup_status(run_id, version, build, stage="failed", status="failed", details={"error_class": type(exc).__name__, "error": safe_text(exc, 800)})
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        runtime.capture_critical(
            trigger="uncaught-fatal-server-exception",
            error=exc,
            safety_containment="The local HTTP server was stopped before diagnostic collection. No external service or live business action was invoked.",
            intended_recovery="Review diagnostics/server.log and the latest crash capsule, rerun the release verifier, then relaunch through OperationsIntelligence.bat.",
        )
        print(f"Local demo failed: {type(exc).__name__}: {safe_text(exc, 1200)}", file=sys.stderr)
        return 1
    finally:
        refresh_stop.set()
        if refresh_thread is not None:
            refresh_thread.join(timeout=1.5)
        if server is not None:
            try:
                server.server_close()
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify and serve the Operations Intelligence portfolio demo.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Preferred loopback port; use 0 for an OS-selected port.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser.")
    parser.add_argument("--check", action="store_true", help="Verify the release and exit without starting a server.")
    parser.add_argument("--diagnostic-self-test", action="store_true", help="Run one controlled critical diagnostic capture and exit.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
