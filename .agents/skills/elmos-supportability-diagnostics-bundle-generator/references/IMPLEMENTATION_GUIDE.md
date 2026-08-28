# Implementation Guide — Supportability and Diagnostics Bundle Generator

## Purpose

Generate privacy-safe self-service diagnostic bundles with versions, health, topology, recent errors and evidence links for customer support.

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

1. collect bounded health and configuration metadata
2. redact secrets and tenant content
3. include reproducible checks and correlation IDs
4. sign and expire support bundles
5. verify offline readability and integrity

## Native acceptance corpus

- `ELMOS_SUPPORTABILITY_DIAGNOSTICS_BUNDLE_GENERATOR-01` — native scenario: collect bounded health and configuration metadata
- `ELMOS_SUPPORTABILITY_DIAGNOSTICS_BUNDLE_GENERATOR-02` — native scenario: redact secrets and tenant content
- `ELMOS_SUPPORTABILITY_DIAGNOSTICS_BUNDLE_GENERATOR-03` — native scenario: include reproducible checks and correlation IDs
- `ELMOS_SUPPORTABILITY_DIAGNOSTICS_BUNDLE_GENERATOR-04` — native scenario: sign and expire support bundles
- `ELMOS_SUPPORTABILITY_DIAGNOSTICS_BUNDLE_GENERATOR-05` — native scenario: verify offline readability and integrity

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
