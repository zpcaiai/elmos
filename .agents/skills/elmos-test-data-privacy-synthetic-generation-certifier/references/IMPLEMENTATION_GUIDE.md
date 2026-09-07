# Implementation Guide — Test Data Privacy and Synthetic Generation Certifier

## Purpose

Generate representative synthetic/subset data with privacy guarantees, referential integrity, rare-case coverage and measured fidelity.

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

1. classify production data use constraints
2. generate synthetic relational and event histories
3. preserve key distributions and edge cases
4. measure privacy attack and fidelity metrics
5. version and expire data sets

## Native acceptance corpus

- `ELMOS_TEST_DATA_PRIVACY_SYNTHETIC_GENERATION_CERTIFIER-01` — native scenario: classify production data use constraints
- `ELMOS_TEST_DATA_PRIVACY_SYNTHETIC_GENERATION_CERTIFIER-02` — native scenario: generate synthetic relational and event histories
- `ELMOS_TEST_DATA_PRIVACY_SYNTHETIC_GENERATION_CERTIFIER-03` — native scenario: preserve key distributions and edge cases
- `ELMOS_TEST_DATA_PRIVACY_SYNTHETIC_GENERATION_CERTIFIER-04` — native scenario: measure privacy attack and fidelity metrics
- `ELMOS_TEST_DATA_PRIVACY_SYNTHETIC_GENERATION_CERTIFIER-05` — native scenario: version and expire data sets

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
