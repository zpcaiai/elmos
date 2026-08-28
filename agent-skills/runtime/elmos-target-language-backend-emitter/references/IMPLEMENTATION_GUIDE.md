# Implementation Guide — Target Language Backend Emitter

## Purpose

Emit buildable target repositories from semantic IR using deterministic code generation, bounded synthesis and target-native package, error, concurrency and ownership conventions.

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

1. Lower typed IR into target-native constructs
2. Preserve source maps and symbol identity
3. Separate deterministic generated and user-owned regions
4. Generate build/package/test configuration
5. Bound model edits to unresolved mappings

## Native acceptance corpus

- `ELMOS_TARGET_LANGUAGE_BACKEND_EMITTER-01` — minimal repository build
- `ELMOS_TARGET_LANGUAGE_BACKEND_EMITTER-02` — target idiom conformance
- `ELMOS_TARGET_LANGUAGE_BACKEND_EMITTER-03` — source map fidelity
- `ELMOS_TARGET_LANGUAGE_BACKEND_EMITTER-04` — generated/user region merge
- `ELMOS_TARGET_LANGUAGE_BACKEND_EMITTER-05` — concurrency/error lowering
- `ELMOS_TARGET_LANGUAGE_BACKEND_EMITTER-06` — unsupported construct block

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
