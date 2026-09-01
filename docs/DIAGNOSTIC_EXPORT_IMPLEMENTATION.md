# Diagnostic Export20 Implementation Mapping

The authoritative diagnostic-export rules for this release remain in the **Gateway shared project defaults v2.17.13 source package**, file `DIAGNOSTIC_EXPORT_SPEC.md`, source ZIP SHA-256:

`63BDA0B5F61BA44F18F55C5B75512085ED3A2FE67C575E3406A5877ECD5F4566`

This document does not redefine those rules. It records where the Operations Intelligence & Automation Platform implements them.

| Requirement family | Project implementation |
|---|---|
| Critical trigger after safety containment | `tools/diagnostic_runtime.py` |
| Minimal crash capsule before full export | `tools/diagnostic_runtime.py` |
| One isolated full Export20 when budgets permit | `tools/create_support_export.py` |
| Maximum 20 redacted, high-value items | `tools/create_support_export.py` allowlist, item ceiling, size budget |
| No network/API/Drive/Norton/repair/live action | Exporter performs project-local file reads and ZIP creation only |
| Event/fingerprint/cooldown suppression | `tools/diagnostic_runtime.py` diagnostic state and suppression logic |
| Same-PC exporter lock only | `tools/create_support_export.py` project-local exporter lock |
| Project-local staging | `temp/` under the resolved project root |
| Same-volume temporary ZIP | Exporter stages under the project root before finalization to `exports/` |
| Integrity/count verification before finalization | Exporter reopens the staged ZIP, tests CRC/count, then atomically replaces the final path |
| Redaction | Exporter removes credential-like values, authorization headers, local usernames, private IPs, MAC addresses, and UUIDs from textual evidence |
| Retention bounds | Diagnostic/export retention logic preserves bounded recent/Critical evidence without deleting unknown/user files |
| Release identity evidence | Export includes version/package/manifest/verification/inventory evidence when available |
| One-active-launcher evidence | Export includes launcher-contract and package-inventory evidence when available |

The controlled diagnostic self-test is a deliberate test action and therefore uses the launcher’s terse `Action? [Y/N]` confirmation. Normal handled warnings, ordinary shutdown, and successful runs do not create Critical exports.

Copyright © 2026 Gateway Information Group LLC. All rights reserved.
