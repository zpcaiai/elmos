# Implementation Guide — Semantic Gap Obligation Generator

## Purpose

Convert language, framework and runtime mismatches into explicit preservation, emulation, monitoring or rejection obligations instead of silent best-effort conversion.

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

1. Diff source and target semantic profiles
2. Classify preservable, emulated, monitored and impossible gaps
3. Bind each gap to verifier portfolio and acceptance scenario
4. Require authorized allowedDelta for intentional change
5. Propagate unresolved gaps into certification scope

## Native acceptance corpus

- `ELMOS_SEMANTIC_GAP_OBLIGATION_GENERATOR-01` — null/empty semantics gap
- `ELMOS_SEMANTIC_GAP_OBLIGATION_GENERATOR-02` — integer overflow gap
- `ELMOS_SEMANTIC_GAP_OBLIGATION_GENERATOR-03` — time/Unicode gap
- `ELMOS_SEMANTIC_GAP_OBLIGATION_GENERATOR-04` — exception/error gap
- `ELMOS_SEMANTIC_GAP_OBLIGATION_GENERATOR-05` — concurrency memory-model gap
- `ELMOS_SEMANTIC_GAP_OBLIGATION_GENERATOR-06` — ownership/FFI impossible gap

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
