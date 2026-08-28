# Implementation Guide — Hermetic Remote Build Cache Governor

## Purpose

Govern remote execution and build caches with content addressing, toolchain/environment keys, tenant isolation, provenance and poisoning detection.

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

1. derive complete action cache keys
2. attest remote workers and toolchains
3. segregate tenant and trust domains
4. verify downloaded outputs and provenance
5. invalidate on environment or policy drift

## Native acceptance corpus

- `ELMOS_HERMETIC_REMOTE_BUILD_CACHE_GOVERNOR-01` — native scenario: derive complete action cache keys
- `ELMOS_HERMETIC_REMOTE_BUILD_CACHE_GOVERNOR-02` — native scenario: attest remote workers and toolchains
- `ELMOS_HERMETIC_REMOTE_BUILD_CACHE_GOVERNOR-03` — native scenario: segregate tenant and trust domains
- `ELMOS_HERMETIC_REMOTE_BUILD_CACHE_GOVERNOR-04` — native scenario: verify downloaded outputs and provenance
- `ELMOS_HERMETIC_REMOTE_BUILD_CACHE_GOVERNOR-05` — native scenario: invalidate on environment or policy drift

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
