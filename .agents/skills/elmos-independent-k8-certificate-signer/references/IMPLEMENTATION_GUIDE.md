# Implementation Guide — Independent K8 Certificate Signer

## Purpose

Sign, publish or refuse completion certificates from sealed assurance cases under current certificate policy, authorized signer identity and exact evidence root.

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

1. Verify scope, assurance case and evidence root
2. Enforce policy, competence and waiver state
3. Use protected short-lived or HSM-backed signer
4. Publish certificate plus limitations and revocation endpoint
5. Produce typed blocked result on any critical gap

## Native acceptance corpus

- `ELMOS_INDEPENDENT_K8_CERTIFICATE_SIGNER-01` — valid certificate signing
- `ELMOS_INDEPENDENT_K8_CERTIFICATE_SIGNER-02` — tampered evidence root rejected
- `ELMOS_INDEPENDENT_K8_CERTIFICATE_SIGNER-03` — expired waiver blocks
- `ELMOS_INDEPENDENT_K8_CERTIFICATE_SIGNER-04` — unauthorized signer rejected
- `ELMOS_INDEPENDENT_K8_CERTIFICATE_SIGNER-05` — blocked result generation
- `ELMOS_INDEPENDENT_K8_CERTIFICATE_SIGNER-06` — certificate verification and revocation lookup

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
