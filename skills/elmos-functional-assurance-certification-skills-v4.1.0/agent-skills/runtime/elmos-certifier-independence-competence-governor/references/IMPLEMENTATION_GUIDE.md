# Implementation Guide — Certifier Independence and Competence Governor

## Purpose

Enforce separation of duties, conflict-of-interest controls, assessor competence, witnessed reviews, rotation and audit trails for certification decisions.

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

1. Separate generator, verifier, approver and signer roles
2. Match competence to technology/risk scope
3. Detect organizational and task conflicts
4. Require witnessed/dual review for high assurance
5. Rotate and revoke assessor authority

## Native acceptance corpus

- `ELMOS_CERTIFIER_INDEPENDENCE_COMPETENCE_GOVERNOR-01` — independent assignment
- `ELMOS_CERTIFIER_INDEPENDENCE_COMPETENCE_GOVERNOR-02` — insufficient competence blocks
- `ELMOS_CERTIFIER_INDEPENDENCE_COMPETENCE_GOVERNOR-03` — self-review denied
- `ELMOS_CERTIFIER_INDEPENDENCE_COMPETENCE_GOVERNOR-04` — conflict declaration
- `ELMOS_CERTIFIER_INDEPENDENCE_COMPETENCE_GOVERNOR-05` — dual review
- `ELMOS_CERTIFIER_INDEPENDENCE_COMPETENCE_GOVERNOR-06` — revoked certifier cannot sign

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
