# Implementation Guide — Hybrid Signature and Certificate Transition Governor

## Purpose

Implement and independently certify hybrid signature and certificate transition governor, including design dual or composite signature profiles for evidence and certificates, manage trust anchors, algorithm identifiers, size limits and verifier compatibility and migrate transparency logs, timestamping and revocation without breaking relying parties.

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

1. design dual or composite signature profiles for evidence and certificates
2. manage trust anchors, algorithm identifiers, size limits and verifier compatibility
3. migrate transparency logs, timestamping and revocation without breaking relying parties
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_HYBRID_SIGNATURE_CERTIFICATE_TRANSITION_GOVERNOR-01` — native scenario: design dual or composite signature profiles for evidence and certificates
- `ELMOS_HYBRID_SIGNATURE_CERTIFICATE_TRANSITION_GOVERNOR-02` — native scenario: manage trust anchors, algorithm identifiers, size limits and verifier compatibility
- `ELMOS_HYBRID_SIGNATURE_CERTIFICATE_TRANSITION_GOVERNOR-03` — native scenario: migrate transparency logs, timestamping and revocation without breaking relying parties
- `ELMOS_HYBRID_SIGNATURE_CERTIFICATE_TRANSITION_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_HYBRID_SIGNATURE_CERTIFICATE_TRANSITION_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
