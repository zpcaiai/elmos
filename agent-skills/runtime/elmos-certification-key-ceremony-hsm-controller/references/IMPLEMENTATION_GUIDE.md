# Implementation Guide — Certification Key Ceremony and HSM Controller

## Purpose

Operate signer key generation, quorum activation, rotation, backup, compromise response and audit for independent K8 certificates.

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

1. define HSM/KMS key ceremony and roles
2. require quorum and witnessed actions
3. rotate keys with certificate continuity
4. publish trust roots and revocation
5. exercise compromise and disaster recovery

## Native acceptance corpus

- `ELMOS_CERTIFICATION_KEY_CEREMONY_HSM_CONTROLLER-01` — native scenario: define HSM/KMS key ceremony and roles
- `ELMOS_CERTIFICATION_KEY_CEREMONY_HSM_CONTROLLER-02` — native scenario: require quorum and witnessed actions
- `ELMOS_CERTIFICATION_KEY_CEREMONY_HSM_CONTROLLER-03` — native scenario: rotate keys with certificate continuity
- `ELMOS_CERTIFICATION_KEY_CEREMONY_HSM_CONTROLLER-04` — native scenario: publish trust roots and revocation
- `ELMOS_CERTIFICATION_KEY_CEREMONY_HSM_CONTROLLER-05` — native scenario: exercise compromise and disaster recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
