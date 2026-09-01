# Closed-Loop Automation Design

## Control model

v0.3.0 uses an explicit:

```text
Trigger → Logic → Action → Case → Playbook → Outcome → Value
```

model.

## Rule authority

`config/automation_catalog.json` is the rule-definition authority. A rule includes:

- id/name/description;
- enabled state;
- severity;
- owner role;
- numeric metric conditions;
- cooldown;
- dedupe key;
- bounded action definition.

## Static simulation

The static showcase can evaluate current metrics against rules and return `Simulated` or `No Match`. It cannot perform a governed server write.

## Governed execution

The local server requires an authenticated role with `run_automation`, a valid CSRF token, same-origin request context, and JSON content. It then:

1. evaluates rule conditions;
2. builds a fingerprint from the rule/evidence boundary;
3. checks equivalent open work;
4. applies cooldown/deduplication;
5. creates a project-local workflow case only when allowed;
6. stores the execution result and evidence;
7. records an audit event.

Execution states include `Triggered`, `Suppressed`, `No Match`, and `Simulated`.

## Noise controls

The analytical layer also summarizes candidate versus consolidated alerts and documents why correlated or repeated signals are suppressed. The goal is to avoid converting every metric anomaly into duplicate management work.

## Playbooks

`config/playbook_catalog.json` defines reusable operational response sequences. Governed playbook runs persist:

- selected playbook;
- optional case link;
- actor;
- current step;
- step completion state;
- run status/timestamps.

## Value realization

Problem and improvement evidence is stored separately from the automation rule itself. This prevents a rule firing from being misrepresented as a successful business outcome.

The demonstration initiatives track baseline, target, measured value, confidence, and synthetic value estimates. These are portfolio examples, not financial guarantees.

## External-write boundary

No third-party write-back is enabled. A future production connector would require a separately approved adapter, credential handling, idempotency/retry semantics, explicit write authorization, and environment-specific safety review.
