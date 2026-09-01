# Operations Intelligence & Automation Platform

**A service-operations command center that connects trusted metrics, explainable analysis, controlled automation, and measured follow-through.**

Version **0.3.1** · build `OIAP-0.3.1-20260831-FIELDLOG1`

## Overview

This project demonstrates a complete operational decision loop rather than a standalone dashboard. It turns service-operation records into trusted metrics, explains where work is breaking down, converts evidence into controlled action, tracks follow-through, and measures whether improvement occurred.

The primary decision chain is:

```text
Raw Data
  ↓
Validation / Quarantine
  ↓
Governed KPI Layer
  ↓
Process Intelligence
  ↓
Root-Factor Evidence
  ↓
Trigger → Logic → Action
  ↓
Workflow Case / Playbook
  ↓
Measured Outcome
  ↓
Improvement Value
  ↓
Operational Learning
```

## Capabilities

### Command Center
- Validated KPI population and data-quality score.
- Backlog, service-level performance, resolution time, reopen rate, and closure/intake balance.
- Drill-down to trusted source records.
- Role-aware views for Executive, Analyst, Operator, and Data Steward.

### Process Intelligence
- Derived operational process variants from observed request attributes and outcomes.
- Bottleneck ranking using evidence depth, service-level misses, cycle time, and reopen exposure.
- Process-aware root-factor ranking with contribution and relative risk.
- Explicit association-versus-causality boundary.
- Operational object graph connecting category, team, and location objects.

The source dataset does not contain intermediate workflow timestamps, so the application does **not** invent them. Process paths are transparent analytical derivations, not fabricated event logs.

### Closed-loop automation
- Governed `Trigger → Logic → Action` rule catalog.
- Dry-run/static simulation before action.
- Server-side role authorization for governed execution.
- Cooldowns and deduplication to reduce duplicate operational work.
- Project-local case creation only; no external-system write-back is enabled by default.
- Execution history and evidence capture.

### Problem, improvement, and value management
- Recurring patterns can be registered as problem records.
- Improvement initiatives store baseline, target, measured result, confidence, and ownership.
- Value realization summarizes active/completed initiatives, successful outcomes, synthetic saved-hours estimates, avoided backlog, and service-level movement.
- Estimates are labeled as decision-support estimates, not financial guarantees.

### Guided playbooks
- Reusable operational response sequences.
- Durable current-step tracking in governed mode.
- Playbook progress can be linked to an operational case.
- Designed to make response repeatable and auditable.

### Explainable smart routing
- Deterministic category/team suggestions for incoming request text.
- Confidence, reasons, and alternatives are visible.
- Human acceptance/override remains the operational boundary.
- This is an explainability demonstration, not a claim of production machine-learning accuracy.

### Personalized operational intelligence
- Pulse-style role-aware metric signals.
- Grounded Operations Analyst for common SLA, backlog, bottleneck, quality, automation, and priority questions.
- Answers expose evidence, assumptions, and follow-up investigation paths.
- The local analyst does not require an external model and does not fabricate records.

### Forecasting and scenario evaluation
- Six-week backlog scenario comparison.
- Demand and capacity adjustments.
- Day-of-week seasonality.
- Queue-aging and workload-mix constraints.
- 80% planning interval.
- 28-day held-out backtest with MAE and bias.

## Deterministic demonstration baseline

The included synthetic dataset contains **1,354 service requests** covering April 27 through August 24, 2026. The data intentionally contains a billing deterioration signal, location concentration, a smaller demand spike, a documented workflow improvement, and bounded quality defects.

Current deterministic results include:

- Trusted KPI population: **1,335 / 1,354** rows.
- Data-quality score: **97.6%**.
- Open backlog: **37**.
- Seven-day backlog change: **+76.2%**.
- SLA attainment: **56.1%**.
- Closure-to-intake ratio: **0.84**.
- South Service Center contributes **40.2%** of recent SLA misses with **1.46× relative risk**.
- 28-day forecast backtest MAE: approximately **3.21 requests/day**.
- Backtest mean bias: approximately **-0.21 requests/day**.

## Two truthful operating modes

### Governed local mode
Run through the Windows launcher or Python local server. It provides:

- project-local SQLite state in WAL mode;
- controlled, append-only database migrations;
- server-validated portfolio demo identities;
- HttpOnly `SameSite=Strict` sessions;
- server-side RBAC;
- CSRF and same-origin protection;
- idempotent ingestion and durable quality evidence;
- KPI versions, cases, audit history, backtests, automation executions, problems, initiatives, and playbook runs;
- scheduled refresh through a bounded source-adapter registry.

The local identities are a portfolio demonstration boundary and are **not** production SSO.

### Static showcase mode
The committed `dist/` bundle can be hosted as a portable public demonstration. It provides analytics, process intelligence, simulation, routing, role views, and grounded local questions without pretending to provide server-side authorization or durable shared state.

## Data governance

The data contract is defined in `config/data_contract.json`. KPI definitions are defined in `config/kpi_catalog.json`. Closed-loop control catalogs are defined in:

- `config/automation_catalog.json`
- `config/playbook_catalog.json`
- `config/improvement_catalog.json`
- `config/slo_catalog.json`
- `config/source_connectors.json`

Blocking defects remain visible in the quality exception register but are excluded from trusted KPI calculations. Identical accepted datasets are SHA-256 idempotent.

## Durable operational model

SQLite migrations live under `db/migrations/` and currently cover:

1. governed ingestion, quality, cases, audit, and outcomes;
2. KPI versions and alert-review/SLO evidence;
3. forecast evaluations and refresh/source-adapter state;
4. automation rules/executions, problem records, improvement initiatives, playbooks, and playbook runs.

See `docs/DATA_MODEL.md` for the table-level map.

## Windows launcher

Extract the full ZIP to a normal local folder and run:

```text
OperationsIntelligence.bat
```

The launcher derives the project root from its own location. It does not use Desktop, Downloads, or the current working directory as the runtime root.

The project intentionally ships one active BAT/CMD launcher. The launcher/action registry is checked by the release contract tests.

## Release integrity

Before governed local services are exposed, the project verifies version/build coherence across:

- `VERSION.txt`
- `PACKAGE_METADATA.json`
- `MANIFEST.json`
- `SBOM.json`
- compiled release identity
- every managed runtime-critical SHA-256/size entry

The gate fails closed on disagreement.

## Key tests

The release test suite covers:

- deterministic KPI and data-quality behavior;
- process variants, root factors, object graph, opportunity scoring, alert consolidation, smart routing, and grounded operational questions;
- SQLite migrations and closed-loop durable state;
- automation simulation, governed execution, deduplication/cooldown, cases, improvements, and playbooks;
- RBAC/CSRF/origin/content-type protections;
- one-active-launcher and runtime-file contract;
- fail-closed release identity;
- HTTP security/readiness;
- compiled desktop/mobile browser rendering;
- release packaging, duplicate classification, and bounded diagnostic exports.

## Important limitations

- The dataset is synthetic and designed for demonstration.
- Derived process paths are not a substitute for a real event log with intermediate stage timestamps.
- Root-factor signals are associative, not causal proof.
- Automation opportunity/value numbers are synthetic prioritization estimates, not guaranteed savings.
- Local demo authentication is not a replacement for enterprise identity.
- SQLite is not presented as a shared enterprise database.
- The shipped source adapter is local and bounded; no live third-party connector is claimed.
- External operational write-back is disabled by default.
- Real enterprise deployment would require managed identity, secrets, durable shared infrastructure, approved connectors, and environment-specific security review.

## Portfolio discussion

This project is intended to demonstrate practical overlap across data analysis, business analysis, BI, data governance, operations, program management, analytics engineering, process intelligence, workflow automation, and technical consulting.
