# Implementation Guide — Language Semantic Profile Compiler

## Purpose

Compile exact-version language semantics for types, nullability, numeric behavior, Unicode, exceptions, concurrency, ownership, async, reflection, FFI and build/runtime boundaries.

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

1. Fingerprint compiler and runtime rather than language name only
2. Represent type, value, control, effect and concurrency semantics
3. Capture implementation-defined and undefined behavior
4. Bind build system and package ecosystem semantics
5. Emit profile-specific proof obligations

## Native acceptance corpus

- `ELMOS_LANGUAGE_SEMANTIC_PROFILE_COMPILER-01` — Java overflow/null profile
- `ELMOS_LANGUAGE_SEMANTIC_PROFILE_COMPILER-02` — Python dynamic dispatch profile
- `ELMOS_LANGUAGE_SEMANTIC_PROFILE_COMPILER-03` — TypeScript erased-type runtime profile
- `ELMOS_LANGUAGE_SEMANTIC_PROFILE_COMPILER-04` — C# async/exception profile
- `ELMOS_LANGUAGE_SEMANTIC_PROFILE_COMPILER-05` — Rust ownership/unsafe profile
- `ELMOS_LANGUAGE_SEMANTIC_PROFILE_COMPILER-06` — profile round-trip and source-map test

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
