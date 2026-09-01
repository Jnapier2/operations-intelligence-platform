# Netlify Deployment — Static Portfolio Showcase

Netlify is a **static showcase boundary** for v0.3.0. It publishes the compiled `dist/` bundle and can host the optional bounded aggregate-summary function when deliberately configured.

## What the static site demonstrates

- validated local CSV analysis;
- deterministic KPIs and drill-down;
- process variants, bottlenecks, root-factor evidence, and object relationships;
- Pulse-style role signals;
- grounded local Operations Analyst questions;
- Trigger → Logic → Action **simulation**;
- automation opportunity scoring;
- explainable routing;
- browser-local reversible case edits;
- management/report exports.

## What the static site intentionally does not claim

It does not provide:

- server-enforced RBAC;
- durable shared SQLite state;
- governed automation execution;
- durable playbook progress;
- production SSO;
- live third-party connectors;
- external operational write-back.

Those boundaries are explicit in the application.

## Build/publish contract

The committed `netlify.toml` verifies the release before publishing `dist/`. Static assets are generated from the authoritative source/config catalogs and release identity is embedded in the bundle.

The static ZIP is suitable for a simple preview. It contains only the verified `dist/` payload and does not contain the local governed service or database.

## Optional aggregate summary

The optional serverless summary route is separate from the grounded local Operations Analyst. It is disabled unless deliberately configured and rejects raw-record payloads. No secret is required for the core static showcase.

## Deployment verification

After deployment, verify:

1. Command Center loads.
2. Process Intelligence renders common paths and root-factor boundary text.
3. Automation & Improvement loads all static catalogs and can simulate rules.
4. Operations Analyst returns evidence-grounded local answers.
5. Static mode is clearly identified.
6. No console errors occur.
7. CSV download/export actions remain functional.
