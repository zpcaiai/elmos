---
name: external-service-virtualization-record-replay
description: "Virtualize and record/replay external HTTP, RPC, payment, identity, mail, SMS and other services for Batch 9. Use to give source and target identical safe responses and faults."
---

# External Service Virtualization Record Replay

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Define bounded request matching and redacted interaction records.
2. Replay identical response, virtual latency and fault sequence to both runtimes.
3. Compare calls, ordering, retries, correlation and non-idempotent behavior.

## Hard rules

- Never contact real payment, notification or production services.
- Do not use broad replay matching or real credentials.
- Keep external calls themselves as observable effects.

## Output

Emit auditable interaction recordings, match reports and fault evidence.

