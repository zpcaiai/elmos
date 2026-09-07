---
name: log-audit-and-observability-event-comparator
description: "Compare Batch 9 audit, security, compliance, billing, business and key observability events. Use when event presence, actor, tenant, outcome or correlation is contract-relevant."
---

# Log Audit and Observability Event Comparator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Classify debug/operational signals separately from required audit and security events.
2. Compare event type, actor, tenant, resource, outcome, fields and causal order.
3. Scan target events for newly exposed sensitive data.

## Hard rules

- Do not require identical framework log formatting.
- Never downgrade missing audit/security events to debug noise.
- Preserve correlation mappings while normalizing trace identifiers.

## Output

Emit missing, duplicate, sensitive and correlation event differences.

