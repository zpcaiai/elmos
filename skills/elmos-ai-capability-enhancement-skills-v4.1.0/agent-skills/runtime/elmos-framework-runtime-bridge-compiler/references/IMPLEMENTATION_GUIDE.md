# Implementation Guide — Framework Runtime Bridge Compiler

## Purpose

Compile framework lifecycle, dependency injection, routing, state, transaction, security, streaming and observability semantics across language targets.

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

1. Model framework startup/shutdown and request lifecycle
2. Map DI scope, middleware and exception boundaries
3. Preserve transaction/security/session semantics
4. Compile streaming and backpressure contracts
5. Emit bridge adapters only where direct lowering is impossible

## Native acceptance corpus

- `ELMOS_FRAMEWORK_RUNTIME_BRIDGE_COMPILER-01` — DI scope equivalence
- `ELMOS_FRAMEWORK_RUNTIME_BRIDGE_COMPILER-02` — route and middleware order
- `ELMOS_FRAMEWORK_RUNTIME_BRIDGE_COMPILER-03` — transaction propagation
- `ELMOS_FRAMEWORK_RUNTIME_BRIDGE_COMPILER-04` — security filter chain
- `ELMOS_FRAMEWORK_RUNTIME_BRIDGE_COMPILER-05` — stream cancellation/backpressure
- `ELMOS_FRAMEWORK_RUNTIME_BRIDGE_COMPILER-06` — startup/shutdown lifecycle

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
