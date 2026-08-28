# Implementation Guide — Sensitive Data Masking and Tokenization Certifier

## Purpose

Generate and verify deterministic/non-deterministic masking, tokenization, format preservation, referential integrity and re-identification controls across environments.

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

1. discover and classify sensitive fields
2. select masking/tokenization by purpose
3. preserve joins and test realism where authorized
4. verify key rotation and vault isolation
5. measure re-identification and leakage risk

## Native acceptance corpus

- `ELMOS_SENSITIVE_DATA_MASKING_TOKENIZATION_CERTIFIER-01` — native scenario: discover and classify sensitive fields
- `ELMOS_SENSITIVE_DATA_MASKING_TOKENIZATION_CERTIFIER-02` — native scenario: select masking/tokenization by purpose
- `ELMOS_SENSITIVE_DATA_MASKING_TOKENIZATION_CERTIFIER-03` — native scenario: preserve joins and test realism where authorized
- `ELMOS_SENSITIVE_DATA_MASKING_TOKENIZATION_CERTIFIER-04` — native scenario: verify key rotation and vault isolation
- `ELMOS_SENSITIVE_DATA_MASKING_TOKENIZATION_CERTIFIER-05` — native scenario: measure re-identification and leakage risk

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
