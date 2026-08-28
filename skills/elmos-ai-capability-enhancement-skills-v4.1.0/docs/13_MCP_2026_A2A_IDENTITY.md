# MCP 2026, A2A v1 and Agent Identity

The protocol plane is versioned and negotiated. The core models MCP `2026-07-28`, extension negotiation, Tasks, Skills, Apps and enterprise authorization. A2A v1 Agent Cards are signed, expiry-bound, tenant-aware and linked to workload/delegated identities.

## Four identities

1. Human principal.
2. Logical agent.
3. Runtime workload.
4. Downstream delegated principal.

No identity implies another. Token exchange may only reduce authority. Every tool request binds audience, resource, tenant, environment, execution epoch and action digest.

## Durable Task refinement

`MCP Task ↔ Elmos Run/Step/ExecutionEpoch/Checkpoint`. Duplicate polls are idempotent; stale fencing is rejected; cancellation cannot report complete until external side effects are reconciled.
