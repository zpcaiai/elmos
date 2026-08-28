# Implementation Guide — Certification Policy and Practice Authority

## Purpose

Define versioned certificate policies and certification practice statements for assurance levels, evidence classes, validity, revocation, audits and signer operations.

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

1. Define claim/status semantics and assurance levels
2. Specify required verifier independence and evidence
3. Define signer, key, validity and revocation practices
4. Control policy changes and grandfathering
5. Publish customer-readable certificate limitations

## Native acceptance corpus

- `ELMOS_CERTIFICATION_POLICY_PRACTICE_AUTHORITY-01` — A1/A2/A3 evidence profile
- `ELMOS_CERTIFICATION_POLICY_PRACTICE_AUTHORITY-02` — policy version binding
- `ELMOS_CERTIFICATION_POLICY_PRACTICE_AUTHORITY-03` — signer practice compliance
- `ELMOS_CERTIFICATION_POLICY_PRACTICE_AUTHORITY-04` — policy change recertification
- `ELMOS_CERTIFICATION_POLICY_PRACTICE_AUTHORITY-05` — certificate limitation rendering
- `ELMOS_CERTIFICATION_POLICY_PRACTICE_AUTHORITY-06` — revocation process test

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
