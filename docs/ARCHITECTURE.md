# Architecture — Operations Intelligence & Automation Platform v0.3.0

## Architectural goal

Keep one coherent decision system from data trust through operational learning while preserving a portable public showcase and a governed local demonstration.

## Operating modes

### Static showcase

`dist/` contains the portable application. It can:

- load and validate the deterministic demo or a local CSV;
- calculate KPIs, alerts, scenarios, process variants, bottlenecks, root factors, and object relationships;
- simulate automation rules;
- provide explainable routing and grounded local operational questions;
- maintain reversible browser-local workflow edits.

It does not claim server-side authorization or shared durable state.

### Governed local mode

`tools/serve_demo.py` exposes the same compiled application plus governed APIs backed by project-local SQLite. It adds:

- server-validated portfolio demo identities;
- HttpOnly SameSite sessions;
- RBAC, CSRF, same-origin, and JSON-only write protection;
- durable ingestion, cases, audit events, outcomes, KPI versions, alert reviews, forecast evaluations, automation executions, problems, initiatives, and playbook runs;
- controlled local source refresh;
- startup/readiness evidence and bounded diagnostics.

## Logical layers

```text
Browser presentation
  ├─ Command Center / Analysis Lab
  ├─ Process Intelligence
  ├─ Automation & Improvement
  ├─ Operations Analyst / Pulse
  ├─ Workflow / Governance / System Health
  └─ Record Explorer
        ↓
Analytical domain
  ├─ csv.ts             validation + trusted data boundary
  ├─ analytics.ts       KPIs + alerts + scenarios + recommendations
  ├─ intelligence.ts    process variants + root factors + object graph
  │                     + pulse + routing + opportunities + grounded Q&A
  └─ api.ts             governed API client boundary
        ↓
Governed local service
  ├─ platform_api.py    sessions + RBAC + protected endpoints
  ├─ operational_store.py
  │     ├─ ingestion / KPI / cases / outcomes
  │     ├─ automation rules + executions
  │     ├─ problems + initiatives
  │     └─ playbooks + runs
  ├─ source_connectors.py
  └─ diagnostic_runtime.py
        ↓
Project-local SQLite
  └─ db/migrations/001…004
```

## Authoritative configuration

- `config/data_contract.json` — ingestion schema, controlled values, freshness/quality rules.
- `config/kpi_catalog.json` — governed KPI semantic definitions.
- `config/slo_catalog.json` — analytical-system service levels.
- `config/source_connectors.json` — bounded ingestion adapter registry.
- `config/automation_catalog.json` — Trigger → Logic → Action rule definitions.
- `config/playbook_catalog.json` — reusable operational response sequences.
- `config/improvement_catalog.json` — synthetic problem/improvement demonstration evidence.

The static build copies the three presentation-required closed-loop catalogs into `dist/data/`; duplicate scanning classifies those copies as intentional config-to-production boundaries.

## Process-intelligence method

The synthetic service dataset has request-level creation/closure/outcome fields but not a complete event history for every intermediate workflow state. `src/intelligence.ts` therefore derives process variants from observable dimensions/outcomes instead of manufacturing timestamps.

The release supports:

- variant frequency/share;
- SLA miss and reopen exposure;
- median cycle time;
- bottleneck scoring;
- root-factor contribution/relative risk;
- category/team/location object relationships.

All root-factor language is association-only.

## Automation boundary

Automation rules are declarative catalog entries. Governed evaluation checks conditions against bounded analytical metrics. Execution is intentionally constrained:

1. authenticate role;
2. validate CSRF/origin/content type;
3. evaluate all conditions;
4. derive fingerprint;
5. check existing equivalent open work;
6. apply rule cooldown/deduplication;
7. create only a project-local workflow case;
8. record execution evidence and audit event.

No network write-back or third-party credential is required or enabled.

## Operations Analyst boundary

The local analyst is deterministic and evidence-grounded. It selects from current KPI/process/quality/automation evidence and returns:

- answer;
- evidence list;
- caveat/boundary;
- suggested follow-up questions.

It is deliberately separate from the optional aggregate-summary endpoint so core portfolio Q&A remains functional offline and does not require a secret.

## Release identity

Before authenticated/preflight work, the launcher verifies a coherent version/build across release metadata and SHA-256/size for all managed runtime-critical files. Runtime-managed scope includes compiled assets, governed service modules, configs, and all database migrations.

One active BAT/CMD launcher is allowed: `OperationsIntelligence.bat`.

## Production boundary

A real enterprise deployment would replace or extend the portfolio foundation with:

- enterprise SSO/OIDC;
- managed relational storage and backup/recovery;
- secrets management;
- approved incremental connectors and dead-letter/retry handling;
- explicit external write-back permissions;
- multi-user concurrency and tenancy controls;
- environment-specific monitoring and security review.

The portfolio package does not claim those deployment controls are already present.
