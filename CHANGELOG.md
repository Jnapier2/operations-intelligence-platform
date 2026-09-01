# Changelog

## 0.3.1 — Field Log Hygiene & Evidence Hardening — 2026-08-31

Build: `OIAP-0.3.1-20260831-FIELDLOG1`

### Fixed
- Sanitizes malformed TLS/non-HTTP request diagnostics at the HTTP logging boundary so binary-looking extended characters cannot leak into `server.log`.
- Escapes non-ASCII wire noise again when synthesizing `diagnostics/latest_startup_run.log`, so older/noisy server logs cannot contaminate Export20 evidence.
- Removes the stale `OperationsIntelligenceLocal/0.2` HTTP server-version marker; release identity remains authoritative through `/__health`.
- Finalizes `latest_startup_status.json` after the controlled diagnostic self-test instead of leaving the evidence state at `in_progress`.
- Expands HTTP smoke coverage to include extended wire-noise sanitation and the stable local-server header contract.

### Field evidence reconciled
- Reviewed Windows v0.3.0 manual support export SHA-256 `330300AF3623C98C789B4445D41087738BA5803D40142A3B18A0E2F37DB81425`.
- Field run reached `http_ready`, verified 46/46 managed runtime files, served all new intelligence assets, established a governed demo session, and returned governed API data successfully.
- The field export exposed raw extended TLS-probe bytes in current-run logs despite the existing control-character sanitizer; v0.3.1 closes that diagnostic-hygiene gap without changing business logic.

### Rollback
- Preserve exact v0.3.0 full release SHA-256 `84A3D9304CBF8A080B97D5C267902E8FCF49D6D1F21F62191A6F206805B1F754` as the Windows field-confirmed functional rollback, with the known diagnostic-log hygiene caveat above.

## 0.3.0 — Process Intelligence & Closed-Loop Automation — 2026-08-31

Build: `OIAP-0.3.0-20260831-CLOSEDLOOP1`

### Added

- Process Intelligence Explorer with derived process variants, bottleneck ranking, rework/SLA exposure, and explicit method boundaries.
- Process-aware root-factor analysis with support, miss contribution, relative risk, and association-only language.
- Operational object graph connecting category, team, and location objects.
- Role-aware Pulse signals and an evidence-grounded local Operations Analyst.
- Explainable deterministic request classification/routing with confidence, reasons, alternatives, and human-override boundary.
- Declarative Trigger → Logic → Action automation catalog.
- Static rule simulation plus governed server execution with RBAC, CSRF, deduplication, cooldown, local case creation, and execution history.
- Alert signal-to-noise summary and suppression reasoning.
- Automation opportunity scoring with bounded synthetic time/cycle estimates.
- Problem management records, improvement initiatives, and Value Realization metrics.
- Reusable guided playbooks with durable governed run progress.
- SQLite migration `004_closed_loop_intelligence.sql` for rules, executions, problems, initiatives, playbooks, and playbook runs.
- New static production catalogs for automation, playbooks, and improvement evidence.
- Browser acceptance coverage for Process Intelligence, Automation & Improvement, and Operations Analyst.
- Management-brief process-intelligence and automation-opportunity sections.
- Recruiter case study/demo documentation updated to reflect the actual governed v0.3.0 platform.

### Safety / truth boundaries

- No intermediate process-event timestamps are invented; process variants are transparently derived from available request attributes/outcomes.
- Root-factor evidence is associative and does not claim causality.
- Static hosting simulates automation; governed writes require the local server.
- Governed automation creates only project-local cases; external operational write-back remains disabled.
- Automation/value estimates are labeled estimates rather than guaranteed savings.
- Local portfolio authentication is not represented as enterprise SSO.

### Preserved

- v0.2.1 remains the exact archive-qualified rollback candidate.
- One active BAT/CMD launcher.
- Fail-closed pre-auth/runtime identity checks.
- Project-local SQLite/config/log/state/temp/export boundaries.
- v2.17.13 parameter baseline and source receipt.
- Bounded Export20 diagnostic behavior.

## 0.2.1 — Field Evidence Hardening — 2026-08-31

Preserved as rollback history. Added atomic startup-stage evidence, current-run readiness reporting, loopback health proof, and current-run-only support-log synthesis.

## 0.2.0 — Governed Operational Foundation — 2026-08-29

Preserved as rollback history. Added durable SQLite state, controlled migrations, server-validated demo roles, RBAC/CSRF, idempotent ingestion, governed KPI versions, outcomes, forecast evaluation, source adapters, SLOs, and release-gate expansion.

Earlier release history remains available in archived release artifacts.
