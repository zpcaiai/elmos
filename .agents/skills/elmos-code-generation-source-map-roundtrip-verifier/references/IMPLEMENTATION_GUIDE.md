# Implementation Guide — Code Generation Source-Map Round-Trip Verifier

## Purpose

Verify source-to-IR-to-target lineage, symbol identity, comments, diagnostics, coverage and debugger mappings across regeneration and reverse import.

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

1. map every generated range to IR and source evidence
2. round-trip symbols and stable generated identities
3. preserve user-owned regions and comments
4. translate diagnostics and coverage to source concepts
5. detect stale or ambiguous mappings after merge

## Native acceptance corpus

- `ELMOS_CODE_GENERATION_SOURCE_MAP_ROUNDTRIP_VERIFIER-01` — native scenario: map every generated range to IR and source evidence
- `ELMOS_CODE_GENERATION_SOURCE_MAP_ROUNDTRIP_VERIFIER-02` — native scenario: round-trip symbols and stable generated identities
- `ELMOS_CODE_GENERATION_SOURCE_MAP_ROUNDTRIP_VERIFIER-03` — native scenario: preserve user-owned regions and comments
- `ELMOS_CODE_GENERATION_SOURCE_MAP_ROUNDTRIP_VERIFIER-04` — native scenario: translate diagnostics and coverage to source concepts
- `ELMOS_CODE_GENERATION_SOURCE_MAP_ROUNDTRIP_VERIFIER-05` — native scenario: detect stale or ambiguous mappings after merge

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
