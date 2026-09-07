---
name: http-traffic-capture-and-replay
description: "Capture and safely replay test, contract, fuzz or sanitized traffic to Batch 9 source and target runtimes. Use for endpoint, session, streaming, multipart or concurrent HTTP scenarios."
---

# HTTP Traffic Capture and Replay

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Preserve method, path, query, meaningful headers, cookies, original body, content type, identity and order.
2. Replace credentials with local test identities while preserving principal and tenant semantics.
3. Control disconnect, timeout, streaming, multipart and concurrency during replay.

## Hard rules

- Never persist production tokens or return shadow output to clients.
- Never let replay access production resources.
- Do not parse and reserialize away raw-format test cases.

## Output

Emit redacted request records and replay evidence linked to scenarios.

