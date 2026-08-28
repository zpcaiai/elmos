# Implementation Guide — Runtime Admission and Attestation Controller

## Purpose

Admit only signed, policy-conformant, vulnerability-acceptable and attested artifacts/configurations into execution environments.

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

1. Verify signatures and provenance before deploy
2. Check certificate, SBOM/VEX and policy state
3. Bind configuration and runtime identity
4. Deny mutable tags and unpinned dependencies
5. Continuously re-evaluate on revocation

## Native acceptance corpus

- `ELMOS_RUNTIME_ADMISSION_ATTESTATION_CONTROLLER-01` — signed digest admitted
- `ELMOS_RUNTIME_ADMISSION_ATTESTATION_CONTROLLER-02` — unsigned image denied
- `ELMOS_RUNTIME_ADMISSION_ATTESTATION_CONTROLLER-03` — revoked certificate denied
- `ELMOS_RUNTIME_ADMISSION_ATTESTATION_CONTROLLER-04` — critical KEV denied
- `ELMOS_RUNTIME_ADMISSION_ATTESTATION_CONTROLLER-05` — config digest mismatch
- `ELMOS_RUNTIME_ADMISSION_ATTESTATION_CONTROLLER-06` — post-admission revocation eviction

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
