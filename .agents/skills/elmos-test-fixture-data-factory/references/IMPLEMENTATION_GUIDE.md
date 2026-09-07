# Implementation Guide — Test Fixture and Data Factory

## Purpose

Generate deterministic, privacy-safe, versioned fixtures and edge corpora with referential integrity, data distributions, provenance and deletion rules.

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

1. Generate schema-valid deterministic data
2. Preserve business invariants and referential integrity
3. Include boundary and adversarial distributions
4. De-identify or synthesize sensitive data
5. Version and garbage-collect fixtures safely

## Native acceptance corpus

- `ELMOS_TEST_FIXTURE_DATA_FACTORY-01` — deterministic seed replay
- `ELMOS_TEST_FIXTURE_DATA_FACTORY-02` — referential integrity
- `ELMOS_TEST_FIXTURE_DATA_FACTORY-03` — PII de-identification
- `ELMOS_TEST_FIXTURE_DATA_FACTORY-04` — boundary values
- `ELMOS_TEST_FIXTURE_DATA_FACTORY-05` — large/skewed dataset
- `ELMOS_TEST_FIXTURE_DATA_FACTORY-06` — fixture deletion and retention

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
