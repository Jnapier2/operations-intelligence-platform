# Recruiter Demo Script — v0.3.0

## 7–10 minute walkthrough

### 1. Start with the business problem — 45 seconds

“This is a Service Operations Command Center. The goal is not just to show a dashboard; it demonstrates how trusted operational data becomes an explanation, an owned action, and a measurable result.”

Point out the deterministic dataset, quality score, backlog, SLA attainment, and current management signal.

### 2. Prove data trust — 45 seconds

Open **Data Governance**.

Show:
- governed KPI definitions;
- trusted versus source rows;
- quality dimensions/exceptions;
- visible assumptions and limitations.

Key point: bad records are visible but blocking defects do not silently contaminate trusted KPIs.

### 3. Move from metric to process — 90 seconds

Open **Process Intelligence**.

Show:
- common operational paths;
- highest-risk bottlenecks;
- root-factor contribution and relative risk;
- category/team/location object relationships.

Say explicitly: “This source does not contain intermediate stage timestamps, so these are transparent derived variants—not fabricated process events. The root-factor view is associative, not causal proof.”

### 4. Show closed-loop automation — 90 seconds

Open **Automation & Improvement**.

Show a rule as `Trigger → Logic → Action`, then run **Simulate rules**.

Explain:
- simulation before action;
- cooldown and dedupe;
- governed execution requires server authorization;
- the portfolio action creates only a local case, not an uncontrolled external write.

Point out automation-opportunity scoring and explainable smart routing.

### 5. Show problem management and playbooks — 60 seconds

On the same view:
- show recurring problem records;
- show improvement initiatives;
- start/advance a guided playbook;
- show the Value Realization scorecard.

Key point: the system measures what happened after the recommendation.

### 6. Ask the operation — 60 seconds

Open **Operations Analyst**.

Ask “Why did SLA miss?” or “What should management prioritize?”

Show the evidence list, caveat, and suggested follow-ups. Explain that the local analyst is grounded in current calculations and documented boundaries rather than inventing records.

### 7. Close on engineering discipline — 45 seconds

Open **System Health** or **Product Story**.

Mention:
- project-local SQLite and migrations;
- idempotent ingestion;
- server-enforced portfolio roles;
- forecast backtesting and uncertainty;
- one active launcher;
- fail-closed runtime identity;
- automated application/platform/HTTP/browser/release tests.

### 8. Closing statement

“The project is meant to show the full chain I would use in an operations/data role: establish trust, understand what changed, investigate how the process behaves, prioritize action, govern the response, and measure whether the result improved.”
