#!/usr/bin/env python3
"""Reproducible loopback HTTP smoke tests for the committed production server."""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from diagnostic_runtime import safe_log_text, safe_wire_log_text  # noqa: E402
from operational_store import DEMO_PASSWORD, OperationalStore  # noqa: E402
from platform_api import PlatformApi  # noqa: E402
from serve_demo import HOST, handler_factory, load_identity  # noqa: E402
from verify_release import verify  # noqa: E402

REPORT = ROOT / "reports" / "http_smoke_report.json"
REQUEST_TIMEOUT_SECONDS = 12


class _Logger:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    def log(self, *args: Any, **_kwargs: Any) -> None:
        self.events.append(args)


class _Runtime:
    def __init__(self) -> None:
        self.logger = _Logger()
        self.capture_calls = 0

    def capture_critical(self, **_kwargs: Any) -> dict[str, Any]:
        self.capture_calls += 1
        raise AssertionError("Rejected HTTP requests must not trigger diagnostic capture.")


def request(url: str, *, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, bytes, Any]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def main() -> int:
    version, build = load_identity()
    identity = verify(persist_report=False)
    runtime = _Runtime()
    tests: list[dict[str, Any]] = []

    def check(name: str, condition: bool, details: Any = None) -> None:
        tests.append({"name": name, "passed": bool(condition), "details": details})

    check("release identity precheck", bool(identity.get("passed")), identity.get("errors", []))
    sanitized_log = safe_log_text("TLS\x16probe\r\nnext\tline\x85")
    check(
        "diagnostic log text strips C0/C1 control characters",
        not any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in sanitized_log),
        sanitized_log,
    )
    wire_log = safe_wire_log_text("TLS\x16\u00c6\u00fe\u00be probe")
    check(
        "HTTP wire log escapes non-ASCII protocol noise",
        all(ord(char) < 128 for char in wire_log) and "\\xc6" in wire_log.lower() and "\\xfe" in wire_log.lower(),
        wire_log,
    )
    if not identity.get("passed"):
        payload = {
            "schema_version": 1,
            "project": "Operations Intelligence & Automation Platform",
            "version": version,
            "build": build,
            "passed": False,
            "test_count": len(tests),
            "passed_count": sum(1 for item in tests if item["passed"]),
            "failed_count": sum(1 for item in tests if not item["passed"]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "results": tests,
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print("HTTP smoke blocked by release identity failure.", file=sys.stderr)
        return 1

    temp_dir = tempfile.TemporaryDirectory(prefix="oiap-http-smoke-")
    store = OperationalStore(Path(temp_dir.name) / "operations.db")
    store.ensure_demo_ingested()
    handler = handler_factory(runtime, identity, "http-smoke", version, build, PlatformApi(store, release_passed=True))
    server = ThreadingHTTPServer((HOST, 0), handler)
    server.daemon_threads = True
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    base = f"http://{HOST}:{port}"

    try:
        # Reproduce the field-observed TLS-on-HTTP probe and verify the actual
        # request-handler logging boundary emits ASCII-safe text only.
        with socket.create_connection((HOST, port), timeout=2) as probe_socket:
            probe_socket.settimeout(1)
            probe_socket.sendall(b"\x16\x03\x01\x00\x05\xc6\xfe\xbe\r\n\r\n")
            try:
                probe_socket.recv(256)
            except OSError:
                pass
        time.sleep(0.05)
        http_log_details = [str(event[2]) for event in runtime.logger.events if len(event) >= 3 and event[1] == "HTTP request"]
        check(
            "malformed wire probe is ASCII-safe at the actual HTTP logging boundary",
            bool(http_log_details) and all(all(ord(char) < 128 for char in detail) for detail in http_log_details),
            http_log_details[-3:],
        )

        status, raw, headers = request(base + "/__health")
        health = json.loads(raw.decode("utf-8"))
        check("health endpoint ready", status == 200 and health.get("status") == "ready" and health.get("releaseGate") == "PASS", health)
        check("health identity matches release", health.get("version") == version and health.get("build") == build, {"version": health.get("version"), "build": health.get("build")})

        for path in ("/index.html", "/assets/app.js", "/assets/intelligence.js", "/data/demo_metadata.json", "/data/automation_catalog.json", "/data/playbook_catalog.json", "/data/improvement_catalog.json"):
            try:
                status, raw, _ = request(base + path)
            except TimeoutError as exc:
                raise AssertionError(f"Static asset response did not complete: {path}") from exc
            check(f"static asset {path}", status == 200 and len(raw) > 0, {"status": status, "bytes": len(raw)})

        status, _, headers = request(base + "/index.html")
        security = {
            "content-security-policy": headers.get("Content-Security-Policy"),
            "x-frame-options": headers.get("X-Frame-Options"),
            "x-content-type-options": headers.get("X-Content-Type-Options"),
            "permissions-policy": headers.get("Permissions-Policy"),
        }
        check(
            "local server emits browser security headers",
            status == 200
            and bool(security["content-security-policy"])
            and security["x-frame-options"] == "SAMEORIGIN"
            and security["x-content-type-options"] == "nosniff"
            and bool(security["permissions-policy"]),
            security,
        )
        server_header = headers.get("Server") or ""
        check(
            "local server header is stable and carries no stale implementation version",
            server_header.strip() == "OperationsIntelligenceLocal",
            server_header,
        )

        status, raw, _ = request(base + "/api/session")
        session_state = json.loads(raw.decode("utf-8"))
        check("unauthenticated session endpoint is explicit", status == 200 and session_state.get("authenticated") is False and session_state.get("mode") == "server-governed", session_state)

        login_payload = json.dumps({"userId": "exec-demo", "password": DEMO_PASSWORD}).encode("utf-8")
        status, _, _ = request(base + "/api/auth/demo-login", method="POST", body=login_payload, headers={"Content-Type": "text/plain"})
        check("governed API rejects non-JSON writes", status == 415, {"status": status})

        wrong_login = json.dumps({"userId": "exec-demo", "password": "wrong"}).encode("utf-8")
        status, _, _ = request(base + "/api/auth/demo-login", method="POST", body=wrong_login, headers={"Content-Type": "application/json"})
        check("invalid local demo credentials are rejected", status == 403, {"status": status})

        status, raw, login_headers = request(base + "/api/auth/demo-login", method="POST", body=login_payload, headers={"Content-Type": "application/json"})
        login = json.loads(raw.decode("utf-8"))
        cookie = (login_headers.get("Set-Cookie") or "").split(";", 1)[0]
        csrf = str(login.get("csrfToken") or "")
        check("valid local credential creates HttpOnly SameSite session", status == 200 and bool(cookie) and bool(csrf) and "HttpOnly" in (login_headers.get("Set-Cookie") or "") and "SameSite=Strict" in (login_headers.get("Set-Cookie") or ""), {"status": status, "cookie_flags": login_headers.get("Set-Cookie")})

        status, raw, _ = request(base + "/api/session", headers={"Cookie": cookie})
        authenticated = json.loads(raw.decode("utf-8"))
        check("authenticated session exposes server permissions", status == 200 and authenticated.get("authenticated") is True and "read_governance" in authenticated.get("permissions", []), authenticated.get("permissions"))

        status, raw, _ = request(base + "/api/kpis", headers={"Cookie": cookie})
        kpis = json.loads(raw.decode("utf-8"))
        check("governed KPI catalog is available to authorized role", status == 200 and len(kpis.get("kpis", [])) >= 6, {"status": status, "count": len(kpis.get("kpis", []))})

        backtest_payload = json.dumps({"horizonDays": 28, "meanAbsoluteError": 2.4, "meanBias": -0.3, "observedDailyFlow": 3.2, "modelVersion": "seasonal-capacity-v2"}).encode("utf-8")
        status, raw, _ = request(base + "/api/backtests", method="POST", body=backtest_payload, headers={"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": csrf})
        backtest_first = json.loads(raw.decode("utf-8"))
        status2, raw2, _ = request(base + "/api/backtests", method="POST", body=backtest_payload, headers={"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": csrf})
        backtest_second = json.loads(raw2.decode("utf-8"))
        check("governed forecast backtest endpoint is durable and idempotent", status == 201 and status2 == 201 and backtest_second.get("backtest", {}).get("idempotent") is True and backtest_first.get("backtest", {}).get("id") == backtest_second.get("backtest", {}).get("id"), {"first": backtest_first, "second": backtest_second})

        status, raw, _ = request(base + "/api/observability", headers={"Cookie": cookie})
        obs = json.loads(raw.decode("utf-8"))
        check("system health API exposes SLOs, alert review, and backtest evidence", status == 200 and len(obs.get("measurements", [])) >= 7 and obs.get("alertReview", {}).get("reviewed") == 4 and obs.get("latestBacktest") is not None, {"status": status, "measurements": len(obs.get("measurements", [])), "alertReview": obs.get("alertReview")})

        status, raw, _ = request(base + "/api/automations", headers={"Cookie": cookie})
        automation_state = json.loads(raw.decode("utf-8"))
        check("automation API exposes governed rules and execution history", status == 200 and len(automation_state.get("rules", [])) == 3, {"status": status, "rules": len(automation_state.get("rules", []))})
        automation_metrics = {"backlogChangePct": 76.2, "slaAttainmentPct": 56.1, "trustedRows": 1335, "qualityScore": 97.6, "issueRowCount": 45, "closureToIntakeRatio": 0.84, "openBacklog": 37}
        simulate_payload = json.dumps({"metrics": automation_metrics, "execute": False}).encode("utf-8")
        status, raw, _ = request(base + "/api/automations/evaluate", method="POST", body=simulate_payload, headers={"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": csrf})
        simulated = json.loads(raw.decode("utf-8"))
        check("automation HTTP endpoint supports no-write simulation", status == 200 and len(simulated.get("executions", [])) == 3 and all(item.get("status") == "Simulated" for item in simulated.get("executions", [])), simulated)
        execute_payload = json.dumps({"metrics": automation_metrics, "execute": True}).encode("utf-8")
        status, raw, _ = request(base + "/api/automations/evaluate", method="POST", body=execute_payload, headers={"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": csrf})
        executed = json.loads(raw.decode("utf-8"))
        triggered_case_ids = [item.get("caseId") for item in executed.get("executions", []) if item.get("status") == "Triggered" and item.get("caseId")]
        check("automation HTTP execution creates bounded project-local cases", status == 200 and len(triggered_case_ids) == 3, executed)

        status, raw, _ = request(base + "/api/improvements", headers={"Cookie": cookie})
        improvements = json.loads(raw.decode("utf-8"))
        check("improvement API exposes problems initiatives and value realization", status == 200 and len(improvements.get("problems", [])) >= 2 and improvements.get("value", {}).get("hoursSavedMonthly", 0) > 0, {"status": status, "value": improvements.get("value")})

        status, raw, _ = request(base + "/api/playbooks", headers={"Cookie": cookie})
        playbook_state = json.loads(raw.decode("utf-8"))
        first_playbook = playbook_state.get("playbooks", [{}])[0].get("id")
        check("playbook API exposes reusable guided response definitions", status == 200 and len(playbook_state.get("playbooks", [])) == 3 and bool(first_playbook), {"status": status, "count": len(playbook_state.get("playbooks", []))})
        start_payload = json.dumps({"caseId": triggered_case_ids[0] if triggered_case_ids else None}).encode("utf-8")
        status, raw, _ = request(base + f"/api/playbooks/{first_playbook}/start", method="POST", body=start_payload, headers={"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": csrf})
        started_playbook = json.loads(raw.decode("utf-8"))
        run_id = started_playbook.get("run", {}).get("id")
        advance_payload = b"{}"
        advance_status, advance_raw, _ = request(base + f"/api/playbook-runs/{run_id}", method="PATCH", body=advance_payload, headers={"Content-Type": "application/json", "Cookie": cookie, "X-CSRF-Token": csrf})
        advanced_playbook = json.loads(advance_raw.decode("utf-8"))
        check("guided playbook HTTP flow persists step progress", status == 201 and advance_status == 200 and advanced_playbook.get("run", {}).get("currentStep") == 1, {"start": started_playbook, "advanced": advanced_playbook})

        operator_payload = json.dumps({"userId": "operator-demo", "password": DEMO_PASSWORD}).encode("utf-8")
        status, raw, op_headers = request(base + "/api/auth/demo-login", method="POST", body=operator_payload, headers={"Content-Type": "application/json", "Cookie": cookie})
        operator_login = json.loads(raw.decode("utf-8"))
        op_cookie = (op_headers.get("Set-Cookie") or "").split(";", 1)[0]
        op_csrf = str(operator_login.get("csrfToken") or "")
        status, raw, _ = request(base + "/api/session", headers={"Cookie": cookie})
        superseded = json.loads(raw.decode("utf-8"))
        check("successful role switch invalidates prior server session", status == 200 and superseded.get("authenticated") is False, superseded)
        status, _, _ = request(base + "/api/kpis", headers={"Cookie": op_cookie})
        check("operator role cannot read governed KPI administration data", status == 403, {"status": status})
        status, raw, _ = request(base + "/api/automations", headers={"Cookie": op_cookie})
        operator_automation = json.loads(raw.decode("utf-8"))
        check("operator can review automation rules", status == 200 and len(operator_automation.get("rules", [])) == 3, {"status": status})
        status, _, _ = request(base + "/api/automations/evaluate", method="POST", body=json.dumps({"metrics": automation_metrics, "execute": False}).encode("utf-8"), headers={"Content-Type": "application/json", "Cookie": op_cookie, "X-CSRF-Token": op_csrf})
        check("operator cannot execute or simulate governed automation writes", status == 403, {"status": status})
        case_payload = json.dumps({"title": "HTTP smoke governed case", "owner": "Operator Demo", "baselineValue": 10, "targetValue": 8, "currentValue": 10}).encode("utf-8")
        status, _, _ = request(base + "/api/cases", method="POST", body=case_payload, headers={"Content-Type": "application/json", "Cookie": op_cookie})
        check("governed write requires valid CSRF token", status == 403, {"status": status})
        status, raw, _ = request(base + "/api/cases", method="POST", body=case_payload, headers={"Content-Type": "application/json", "Cookie": op_cookie, "X-CSRF-Token": op_csrf})
        created_case = json.loads(raw.decode("utf-8"))
        check("operator can create authorized workflow case", status == 201 and str(created_case.get("case", {}).get("id", "")).startswith("CASE-"), created_case)

        status, _, _ = request(base + "/api/cases", method="POST", body=case_payload, headers={"Content-Type": "application/json", "Cookie": op_cookie, "X-CSRF-Token": op_csrf, "Sec-Fetch-Site": "cross-site", "Origin": "https://example.invalid"})
        check("cross-site governed writes are rejected", status == 403, {"status": status})

        status, _, _ = request(base + "/..%2FVERSION.txt")
        check("encoded traversal is rejected", status == 400, {"status": status})

        payload = json.dumps({"message": "smoke-test"}).encode("utf-8")
        status, _, _ = request(
            base + "/__diagnostics/critical",
            method="POST",
            body=payload,
            headers={"Content-Type": "text/plain"},
        )
        check("diagnostic endpoint rejects non-JSON content", status == 415, {"status": status})

        status, _, _ = request(
            base + "/__diagnostics/critical",
            method="POST",
            body=payload,
            headers={"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site", "Origin": "https://example.invalid"},
        )
        check("diagnostic endpoint rejects cross-site requests", status == 403, {"status": status})
        check("rejected diagnostic probes create no capture", runtime.capture_calls == 0, {"capture_calls": runtime.capture_calls})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        temp_dir.cleanup()

    failed = [item for item in tests if not item["passed"]]
    payload = {
        "schema_version": 1,
        "project": "Operations Intelligence & Automation Platform",
        "version": version,
        "build": build,
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
    print(f"{payload['passed_count']}/{payload['test_count']} HTTP smoke checks passed.")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
