#!/usr/bin/env python3
"""Loopback API router for governed local portfolio mode."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import SimpleCookie
from typing import Any, Mapping
from urllib.parse import unquote

from operational_store import OperationalStore, ROLE_PERMISSIONS

SESSION_COOKIE = "oiap_session"
MAX_JSON_BODY = 512_000
MAX_CSV_BODY = 8 * 1024 * 1024


@dataclass
class ApiResponse:
    status: int
    payload: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


class PlatformApi:
    def __init__(self, store: OperationalStore, *, release_passed: bool) -> None:
        self.store = store
        self.release_passed = release_passed

    @staticmethod
    def _cookie_token(headers: Mapping[str, str]) -> str | None:
        raw = headers.get("Cookie") or ""
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def session(self, headers: Mapping[str, str]) -> dict[str, Any] | None:
        return self.store.get_session(self._cookie_token(headers))

    @staticmethod
    def _json_body(body: bytes, limit: int = MAX_JSON_BODY) -> dict[str, Any]:
        if not body or len(body) > limit:
            raise ValueError("Request body is missing or too large.")
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("JSON request body must be an object.")
        return parsed

    @staticmethod
    def _is_json(headers: Mapping[str, str]) -> bool:
        return (headers.get("Content-Type") or "").split(";", 1)[0].strip().lower() == "application/json"

    @staticmethod
    def _same_origin(headers: Mapping[str, str]) -> bool:
        fetch_site = (headers.get("Sec-Fetch-Site") or "").strip().lower()
        if fetch_site and fetch_site not in {"same-origin", "none"}:
            return False
        origin = (headers.get("Origin") or "").strip()
        host = (headers.get("Host") or "").strip()
        return not origin or not host or origin in {f"http://{host}", f"https://{host}"}

    def _require_session(self, headers: Mapping[str, str], permission: str | None = None, *, csrf: bool = False) -> tuple[dict[str, Any] | None, ApiResponse | None]:
        session = self.session(headers)
        if session is None:
            return None, ApiResponse(HTTPStatus.UNAUTHORIZED, {"error": "Authentication required.", "code": "AUTH_REQUIRED"})
        if permission and not self.store.authorize(session, permission):
            return None, ApiResponse(HTTPStatus.FORBIDDEN, {"error": "The current role is not authorized for this action.", "code": "RBAC_DENIED"})
        if csrf:
            csrf_token = headers.get("X-CSRF-Token") or ""
            if not self.store.validate_csrf(session, csrf_token):
                return None, ApiResponse(HTTPStatus.FORBIDDEN, {"error": "CSRF validation failed.", "code": "CSRF_FAILED"})
        return session, None

    def handle_get(self, path: str, headers: Mapping[str, str]) -> ApiResponse | None:
        if not path.startswith("/api/"):
            return None
        if path == "/api/session":
            session = self.session(headers)
            if session is None:
                return ApiResponse(HTTPStatus.OK, {"authenticated": False, "mode": "server-governed", "demoUsers": self.store.demo_users()})
            return ApiResponse(HTTPStatus.OK, {
                "authenticated": True,
                "mode": "server-governed",
                "user": {"id": session["user_id"], "displayName": session["display_name"], "role": session["role"]},
                "expiresAt": session["expires_at"],
                "permissions": sorted(ROLE_PERMISSIONS.get(str(session["role"]), set())),
            })
        if path == "/api/cases":
            _, error = self._require_session(headers, "read_cases")
            return error or ApiResponse(HTTPStatus.OK, {"cases": self.store.list_cases()})
        if path == "/api/audit":
            _, error = self._require_session(headers, "read_audit")
            return error or ApiResponse(HTTPStatus.OK, {"audit": self.store.list_audit()})
        if path == "/api/outcomes":
            _, error = self._require_session(headers, "read_cases")
            return error or ApiResponse(HTTPStatus.OK, {"outcomes": self.store.list_outcomes()})
        if path == "/api/kpis":
            _, error = self._require_session(headers, "read_governance")
            return error or ApiResponse(HTTPStatus.OK, {"kpis": self.store.list_kpis(), "contract": self.store.contract})
        if path == "/api/ingestions":
            _, error = self._require_session(headers, "read_governance")
            return error or ApiResponse(HTTPStatus.OK, {"ingestions": self.store.latest_ingestions()})
        if path == "/api/observability":
            _, error = self._require_session(headers, "read_observability")
            return error or ApiResponse(HTTPStatus.OK, self.store.observability(self.release_passed))
        if path == "/api/backtests":
            _, error = self._require_session(headers, "read_governance")
            return error or ApiResponse(HTTPStatus.OK, {"backtests": self.store.list_backtests()})
        if path == "/api/automations":
            _, error = self._require_session(headers, "read_automation")
            return error or ApiResponse(HTTPStatus.OK, {"rules": self.store.list_automation_rules(), "executions": self.store.list_automation_executions()})
        if path == "/api/improvements":
            _, error = self._require_session(headers, "read_improvements")
            return error or ApiResponse(HTTPStatus.OK, {"problems": self.store.list_problems(), "initiatives": self.store.list_improvements(), "value": self.store.value_realization()})
        if path == "/api/playbooks":
            _, error = self._require_session(headers, "read_improvements")
            return error or ApiResponse(HTTPStatus.OK, {"playbooks": self.store.list_playbooks(), "runs": self.store.list_playbook_runs()})
        return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "API route not found."})

    def handle_post(self, path: str, headers: Mapping[str, str], body: bytes) -> ApiResponse | None:
        if not path.startswith("/api/"):
            return None
        if not self._same_origin(headers):
            return ApiResponse(HTTPStatus.FORBIDDEN, {"error": "Cross-site API requests are not accepted.", "code": "ORIGIN_DENIED"})
        if not self._is_json(headers):
            return ApiResponse(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Governed API writes require application/json.", "code": "CONTENT_TYPE_REQUIRED"})
        if path == "/api/auth/demo-login":
            try:
                payload = self._json_body(body, 16_000)
                previous_token = self._cookie_token(headers)
                session = self.store.create_session(str(payload.get("userId") or ""), str(payload.get("password") or ""))
            except (ValueError, json.JSONDecodeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except PermissionError as exc:
                return ApiResponse(HTTPStatus.FORBIDDEN, {"error": str(exc)})
            if previous_token:
                self.store.delete_session(previous_token)
            headers_out = {
                "Set-Cookie": f"{SESSION_COOKIE}={session.token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800",
            }
            return ApiResponse(HTTPStatus.OK, {"authenticated": True, "csrfToken": session.csrf_token, "user": {"id": session.user_id, "displayName": session.display_name, "role": session.role}, "expiresAt": session.expires_at}, headers_out)
        if path == "/api/auth/logout":
            session, error = self._require_session(headers, csrf=True)
            if error:
                return error
            self.store.delete_session(self._cookie_token(headers))
            return ApiResponse(HTTPStatus.OK, {"authenticated": False}, {"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})

        if path == "/api/cases":
            session, error = self._require_session(headers, "manage_cases", csrf=True)
            if error:
                return error
            try:
                payload = self._json_body(body)
                return ApiResponse(HTTPStatus.CREATED, {"case": self.store.create_case(payload, session)})
            except (ValueError, TypeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path.startswith("/api/cases/") and path.endswith("/outcomes"):
            session, error = self._require_session(headers, "record_outcomes", csrf=True)
            if error:
                return error
            case_id = unquote(path.removeprefix("/api/cases/").removesuffix("/outcomes").strip("/"))
            try:
                payload = self._json_body(body)
                return ApiResponse(HTTPStatus.CREATED, {"outcome": self.store.record_outcome(case_id, payload, session)})
            except KeyError:
                return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "Case not found."})
            except (ValueError, TypeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path == "/api/ingest":
            session, error = self._require_session(headers, "ingest_data", csrf=True)
            if error:
                return error
            try:
                payload = self._json_body(body, MAX_CSV_BODY)
                csv_text = str(payload.get("csv") or "")
                if not csv_text or len(csv_text.encode("utf-8")) > MAX_CSV_BODY:
                    raise ValueError("CSV content is missing or exceeds the governed upload limit.")
                result = self.store.ingest_csv(csv_text, str(payload.get("datasetName") or "Uploaded dataset"), str(payload.get("sourceName") or "Browser upload"), session)
                status = HTTPStatus.OK if result.get("status") != "rejected" else HTTPStatus.UNPROCESSABLE_ENTITY
                return ApiResponse(status, {"ingestion": result})
            except (ValueError, json.JSONDecodeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path == "/api/backtests":
            session, error = self._require_session(headers, "record_backtests", csrf=True)
            if error:
                return error
            try:
                payload = self._json_body(body)
                return ApiResponse(HTTPStatus.CREATED, {"backtest": self.store.record_backtest(payload, session)})
            except (ValueError, TypeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path == "/api/refresh":
            session, error = self._require_session(headers, "ingest_data", csrf=True)
            if error:
                return error
            result = self.store.run_scheduled_refresh(force=True)
            self.store.add_audit(session["display_name"], session["role"], "Scheduled source refresh checked", "Ingestion", str(result.get("runId") or "demo-local"), f"Refresh result: {result.get('status')}")
            return ApiResponse(HTTPStatus.OK, {"refresh": result})
        if path.startswith("/api/kpis/") and path.endswith("/versions"):
            session, error = self._require_session(headers, "manage_kpis", csrf=True)
            if error:
                return error
            kpi_id = unquote(path.removeprefix("/api/kpis/").removesuffix("/versions").strip("/"))
            try:
                payload = self._json_body(body)
                return ApiResponse(HTTPStatus.CREATED, {"kpi": self.store.create_kpi_version(kpi_id, payload, session)})
            except KeyError:
                return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "KPI not found."})
            except Exception as exc:
                if exc.__class__.__name__ == "IntegrityError":
                    return ApiResponse(HTTPStatus.CONFLICT, {"error": "That KPI version already exists."})
                if isinstance(exc, (ValueError, TypeError)):
                    return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                raise
        if path == "/api/automations/evaluate":
            session, error = self._require_session(headers, "run_automation", csrf=True)
            if error:
                return error
            try:
                payload = self._json_body(body)
                metrics = payload.get("metrics") or {}
                if not isinstance(metrics, dict):
                    raise ValueError("Automation metrics must be a JSON object.")
                execute = bool(payload.get("execute"))
                return ApiResponse(HTTPStatus.OK, {"executions": self.store.evaluate_automation(metrics, session, execute=execute)})
            except (ValueError, TypeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path.startswith("/api/playbooks/") and path.endswith("/start"):
            session, error = self._require_session(headers, "manage_playbooks", csrf=True)
            if error:
                return error
            playbook_id = unquote(path.removeprefix("/api/playbooks/").removesuffix("/start").strip("/"))
            try:
                payload = self._json_body(body)
                return ApiResponse(HTTPStatus.CREATED, {"run": self.store.start_playbook(playbook_id, str(payload.get("caseId") or "") or None, session)})
            except KeyError:
                return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "Playbook not found."})
            except (ValueError, TypeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "API route not found."})

    def handle_patch(self, path: str, headers: Mapping[str, str], body: bytes) -> ApiResponse | None:
        if not path.startswith("/api/"):
            return None
        if not self._same_origin(headers):
            return ApiResponse(HTTPStatus.FORBIDDEN, {"error": "Cross-site API requests are not accepted.", "code": "ORIGIN_DENIED"})
        if not self._is_json(headers):
            return ApiResponse(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Governed API writes require application/json.", "code": "CONTENT_TYPE_REQUIRED"})
        if path.startswith("/api/cases/"):
            session, error = self._require_session(headers, "manage_cases", csrf=True)
            if error:
                return error
            case_id = unquote(path.removeprefix("/api/cases/").strip("/"))
            try:
                payload = self._json_body(body)
                return ApiResponse(HTTPStatus.OK, {"case": self.store.update_case(case_id, payload, session)})
            except KeyError:
                return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "Case not found."})
            except (ValueError, TypeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        if path.startswith("/api/playbook-runs/"):
            session, error = self._require_session(headers, "manage_playbooks", csrf=True)
            if error:
                return error
            run_id = unquote(path.removeprefix("/api/playbook-runs/").strip("/"))
            try:
                self._json_body(body)
                return ApiResponse(HTTPStatus.OK, {"run": self.store.advance_playbook(run_id, session)})
            except KeyError:
                return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "Playbook run not found."})
            except (ValueError, TypeError) as exc:
                return ApiResponse(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        return ApiResponse(HTTPStatus.NOT_FOUND, {"error": "API route not found."})
