# Process Intelligence Method

## Why this method exists

The demonstration service dataset has request-level creation, closure, assignment, category, priority, SLA, reopen, and outcome evidence. It does **not** contain a complete event log of every intermediate workflow transition.

The analysis should not invent those missing events. v0.3.0 therefore implements a transparent derived-process method.

## Derived path

For each trusted request, a path is assembled from observable attributes/outcomes such as:

```text
Channel → Team → Category → Priority/Rework condition → SLA outcome → Final status
```

The application then groups identical derived paths and reports:

- request count/share;
- closed count;
- SLA miss percentage;
- reopen percentage;
- median resolution hours.

## Bottleneck score

Candidate signals are evaluated across queue/category, team, location, rework, and priority groupings. The score combines supported evidence, SLA miss exposure, observed cycle time, and reopen exposure. A minimum support threshold prevents tiny groups from dominating the ranking.

The score is a prioritization signal, not a causal estimate.

## Root-factor evidence

For supported conditions, the application calculates:

- support;
- miss count;
- miss rate;
- contribution to all misses;
- relative risk versus the remaining population;
- lift.

Every rendered interpretation preserves this boundary:

> The condition is associated with the observed outcome; causality is not established by this analysis.

## Operational object graph

The portfolio graph connects observed Category, Team, and Location objects by co-occurrence in trusted requests. Edge weights indicate support/relationship strength. They do not claim system dependency or causal direction.

## What production process mining would add

A production implementation could ingest a proper event log with:

- case/object identifiers;
- activity names;
- event timestamps;
- actors/resources;
- event/order semantics;
- state transitions;
- optional cost/value attributes.

That would enable true wait-time decomposition, conformance checking, transition-level bottlenecks, and richer object-centric process mining. v0.3.0 deliberately stops short of claiming those capabilities without the necessary evidence.
