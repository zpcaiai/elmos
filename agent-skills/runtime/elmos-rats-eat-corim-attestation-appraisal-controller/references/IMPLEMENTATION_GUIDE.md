# Implementation Guide — RATS, EAT and CoRIM Attestation Appraisal Controller

## Purpose

Implement and independently certify rats, eat and corim attestation appraisal controller, including normalize attestation evidence, endorsements and reference values into appraisal claims, verify freshness, key binding, verifier identity and appraisal policy and emit attestation result with explicit trustworthiness scope and uncertainty.

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

1. normalize attestation evidence, endorsements and reference values into appraisal claims
2. verify freshness, key binding, verifier identity and appraisal policy
3. emit attestation result with explicit trustworthiness scope and uncertainty
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_RATS_EAT_CORIM_ATTESTATION_APPRAISAL_CONTROLLER-01` — native scenario: normalize attestation evidence, endorsements and reference values into appraisal claims
- `ELMOS_RATS_EAT_CORIM_ATTESTATION_APPRAISAL_CONTROLLER-02` — native scenario: verify freshness, key binding, verifier identity and appraisal policy
- `ELMOS_RATS_EAT_CORIM_ATTESTATION_APPRAISAL_CONTROLLER-03` — native scenario: emit attestation result with explicit trustworthiness scope and uncertainty
- `ELMOS_RATS_EAT_CORIM_ATTESTATION_APPRAISAL_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_RATS_EAT_CORIM_ATTESTATION_APPRAISAL_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
