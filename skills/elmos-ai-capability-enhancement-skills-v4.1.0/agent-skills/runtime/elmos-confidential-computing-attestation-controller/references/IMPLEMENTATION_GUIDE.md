# Implementation Guide — Confidential Computing Attestation Controller

## Purpose

Verify enclave/TEE identity, measurement, nonce freshness, workload/image binding, key release and evidence appraisal for sensitive execution.

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

1. request and validate remote attestation evidence
2. bind measurement to signed workload and policy
3. release secrets only after appraisal
4. rotate trust roots and handle revocation
5. record TCB and degraded non-TEE path

## Native acceptance corpus

- `ELMOS_CONFIDENTIAL_COMPUTING_ATTESTATION_CONTROLLER-01` — native scenario: request and validate remote attestation evidence
- `ELMOS_CONFIDENTIAL_COMPUTING_ATTESTATION_CONTROLLER-02` — native scenario: bind measurement to signed workload and policy
- `ELMOS_CONFIDENTIAL_COMPUTING_ATTESTATION_CONTROLLER-03` — native scenario: release secrets only after appraisal
- `ELMOS_CONFIDENTIAL_COMPUTING_ATTESTATION_CONTROLLER-04` — native scenario: rotate trust roots and handle revocation
- `ELMOS_CONFIDENTIAL_COMPUTING_ATTESTATION_CONTROLLER-05` — native scenario: record TCB and degraded non-TEE path

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
