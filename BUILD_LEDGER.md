# Build Ledger — v0.3.1

Canonical project: **Professional Portfolio — Operations Intelligence & Automation Platform**  
Build: `OIAP-0.3.1-20260831-FIELDLOG1`  
Baseline: exact v0.3.0 archive SHA-256 `84A3D9304CBF8A080B97D5C267902E8FCF49D6D1F21F62191A6F206805B1F754`  
Parameter baseline: Gateway shared project defaults v2.17.13

## Critical / High

- Preserved one active launcher: `OperationsIntelligence.bat`.
- Preserved fail-closed release identity before governed service exposure.
- Preserved project-local SQLite/state/log/export boundaries and Export20 controls.
- Repaired field-log sanitation at the HTTP boundary; raw non-ASCII wire noise is escaped before bounded logging.
- Repaired current-run support-log synthesis so historical Latin-1/binary-looking wire bytes are escaped before Export20 finalization.
- Removed stale `/0.2` local HTTP server-version metadata.
- Repaired the diagnostic self-test terminal status so successful Export20 acceptance records `diagnostic_self_test_complete / ready`.

## Normal

- Added regression coverage for C0/C1 + extended wire-noise sanitation.
- Added regression coverage for the normalized local `Server` header.
- Reconciled the August 31 v0.3.0 Windows field evidence and preserved it as rollback evidence.

## Unchanged capability foundation

Process Intelligence, Trigger → Logic → Action automation, Pulse signals, Operations Analyst, problem/improvement management, guided playbooks, ROI evidence, governed SQLite/RBAC, forecast/backtesting, KPI governance, and the deterministic 1,354-row business story remain unchanged from v0.3.0.

## Verification completed on working source tree

- TypeScript compilation: PASS.
- Release identity: **46/46 PASS**.
- Application/analytics/security suite: **33/33 PASS**.
- Governed platform foundation: **32/32 PASS**.
- Launcher/runtime contract: **5/5 PASS**.
- HTTP/auth/RBAC/security/logging suite: **40/40 PASS**.
- Browser acceptance: PASS — 10 assertions / 9 screenshots / 0 console errors / 0 page errors.
- Doctor: PASS — 6 KPI definitions / 7 SLO measurements.
- Replayed the exact uploaded noisy v0.3.0 current-run log through the v0.3.1 exporter sanitizer: 38 non-ASCII wire characters reduced to 0; text/control safety PASS.
- Package preflight: 107 source files before index; 7 intentional build-boundary duplicate groups; 0 unresolved duplicates; 1 active BAT/CMD; 0 aliases; 6 actions.

## Exact-archive qualification boundary

The final ZIP will be frozen only after the source-tree gates above. Exact frozen-ZIP re-extraction, live loopback readiness, Critical diagnostic acceptance, and final support-export evidence are recorded in the external final acceptance receipt so the immutable archive is not modified after qualification.

## External gate

Norton-on testing of the exact final v0.3.1 ZIP remains an external Windows acceptance gate and must not be claimed without evidence.
