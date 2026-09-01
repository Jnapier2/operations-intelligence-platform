# Data Model — v0.3.0

## Analytical source grain

The service-request CSV uses one row per request. Required fields are defined by `config/data_contract.json`.

Trusted metrics exclude rows with blocking quality defects. Quality exceptions remain available for inspection.

## Governed SQLite migrations

### 001 — operational foundation

Core persisted capabilities include:

- ingestion runs and trusted/quarantined evidence;
- workflow cases;
- audit events;
- measured outcomes;
- schema migration tracking.

### 002 — semantic and observability layer

Adds governed KPI definitions/versions and analytical-system review evidence, including alert usefulness/SLO support.

### 003 — evaluation and source-refresh layer

Adds forecast-evaluation evidence and source-adapter/refresh state so scheduled ingestion uses one controlled boundary and backtests are durable/idempotent.

### 004 — closed-loop intelligence

Adds:

#### `automation_rules`
Authoritative runtime copy of governed rule definitions.

Key concepts: rule id, enabled state, severity, owner role, conditions, cooldown, dedupe key, bounded action.

#### `automation_executions`
One evaluation/execution evidence record per rule/fingerprint/status boundary.

Key concepts: evaluated time, status (`Triggered`, `Suppressed`, `No Match`, `Simulated`), reason, evidence JSON, optional created case id.

#### `problem_records`
Recurring operational patterns that merit investigation/improvement ownership.

Key concepts: title, hypothesis, owner, status, evidence.

#### `improvement_initiatives`
Measured change initiatives.

Key concepts: problem link, baseline metric/value, target, measured value, unit, confidence, estimated hours saved, backlog avoided, SLA movement.

The shipped records are synthetic portfolio evidence and are labeled accordingly.

#### `playbooks`
Reusable operational response definitions from the governed catalog.

#### `playbook_runs`
Durable execution state for a selected playbook, including current step, step completion state, actor, optional case link, and status.

## Derived analytical objects

The following are recomputed from trusted request records rather than persisted as a competing source of truth:

- process variants;
- bottleneck scores;
- process-aware root factors;
- operational object graph;
- personalized Pulse signals;
- smart-routing suggestions;
- automation-opportunity scores;
- grounded Operations Analyst answers.

This keeps one authoritative request/KPI foundation while allowing deterministic analytical views to evolve.

## Object graph

The portfolio object graph currently models:

```text
Category ↔ Team
Category ↔ Location
Team ↔ Location
```

Edge weights represent request co-occurrence/support, not causal dependency.

## Data ownership and history

KPI definitions are versioned rather than overwritten. Ingestion content hashes prevent identical accepted datasets from being processed twice. Workflow and improvement evidence is separated from analytical computation so the platform can show what changed after an action.
