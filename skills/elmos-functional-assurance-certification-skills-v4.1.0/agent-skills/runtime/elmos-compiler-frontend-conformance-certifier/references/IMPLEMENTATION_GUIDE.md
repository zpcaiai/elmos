# Implementation Guide — Compiler Frontend Conformance Certifier

## Purpose

Certify compiler-native, lossless and runtime-assisted source frontends against language conformance corpora before their facts may become semantic authority.

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

1. Run compiler-native parse/type/symbol/control/effect probes
2. Compare frontend results with authoritative compiler diagnostics
3. Measure supported construct and dynamic-boundary coverage
4. Quarantine fallback AST/text-only claims
5. Version and revoke frontend certificates

## Native acceptance corpus

- `ELMOS_COMPILER_FRONTEND_CONFORMANCE_CERTIFIER-01` — valid construct corpus
- `ELMOS_COMPILER_FRONTEND_CONFORMANCE_CERTIFIER-02` — invalid program diagnostic parity
- `ELMOS_COMPILER_FRONTEND_CONFORMANCE_CERTIFIER-03` — macro/generated source lineage
- `ELMOS_COMPILER_FRONTEND_CONFORMANCE_CERTIFIER-04` — reflection/dynamic loading detection
- `ELMOS_COMPILER_FRONTEND_CONFORMANCE_CERTIFIER-05` — incremental invalidation correctness
- `ELMOS_COMPILER_FRONTEND_CONFORMANCE_CERTIFIER-06` — compiler upgrade regression

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
