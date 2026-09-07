# ADR-0001 — Account-global three-slot semaphore

## Status
Accepted.

## Context
The product requires every authenticated account to run no more than three root tasks concurrently, even across tenants, devices, and API replicas. Count-then-start races can oversubscribe.

## Decision
Represent the hard limit as exactly three PostgreSQL slot rows per account. Claim, renew, and release use transactions, row locking, lease generation, and idempotent transitions. Redis is optional read acceleration only.

## Consequences
- The invariant is enforceable across replicas.
- Account limits work across tenant memberships.
- Slot reconciliation and stale lease handling are required.
- Tenant/platform/resource limits remain separate.
