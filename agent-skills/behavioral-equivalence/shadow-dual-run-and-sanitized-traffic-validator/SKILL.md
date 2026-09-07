---
name: shadow-dual-run-and-sanitized-traffic-validator
description: "Replay sanitized representative traffic into an isolated target shadow and compare it with source behavior. Use in test or preproduction shadow validation with side effects virtualized."
---

# Shadow Dual Run and Sanitized Traffic Validator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Sample by endpoint, tenant class, data type, risk, error path, size, time and flag.
2. Preserve stateful session order, token replacement, correlation, IDs and seed state.
3. Route every target side effect to isolated databases, topics, stubs, caches and storage.

## Hard rules

- Never return shadow output to a real client or affect source latency.
- Forbid target payment, notification, deletion, scheduler and production writes.
- Bound execution cost and redact all sampled data.

## Output

Emit sanitized sample lineage, isolation proof and shadow comparison reports.

