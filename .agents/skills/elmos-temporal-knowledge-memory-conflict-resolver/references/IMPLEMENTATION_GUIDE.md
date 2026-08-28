# Implementation Guide — Temporal Knowledge and Memory Conflict Resolver

## Purpose

Resolve contradictory, stale and time-scoped facts across documents, tools, user memory and organizational knowledge with provenance and policy.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. represent valid-time and transaction-time facts
2. score source authority and freshness
3. retain disagreement and counterevidence
4. apply user/organization scope and consent
5. generate abstention or review when unresolved

## Native acceptance corpus

- `ELMOS_TEMPORAL_KNOWLEDGE_MEMORY_CONFLICT_RESOLVER-01` — native scenario: represent valid-time and transaction-time facts
- `ELMOS_TEMPORAL_KNOWLEDGE_MEMORY_CONFLICT_RESOLVER-02` — native scenario: score source authority and freshness
- `ELMOS_TEMPORAL_KNOWLEDGE_MEMORY_CONFLICT_RESOLVER-03` — native scenario: retain disagreement and counterevidence
- `ELMOS_TEMPORAL_KNOWLEDGE_MEMORY_CONFLICT_RESOLVER-04` — native scenario: apply user/organization scope and consent
- `ELMOS_TEMPORAL_KNOWLEDGE_MEMORY_CONFLICT_RESOLVER-05` — native scenario: generate abstention or review when unresolved

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
