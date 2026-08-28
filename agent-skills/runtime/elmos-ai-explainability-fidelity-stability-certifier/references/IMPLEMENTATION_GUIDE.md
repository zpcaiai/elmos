# Implementation Guide — Explainability Fidelity and Stability Certifier

## Purpose

Implement and independently certify explainability fidelity and stability certifier, including measure explanation fidelity to model or system decision process, test stability, sensitivity, completeness and audience comprehension and verify explanation supports contestability and does not disclose unsafe information.

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

1. measure explanation fidelity to model or system decision process
2. test stability, sensitivity, completeness and audience comprehension
3. verify explanation supports contestability and does not disclose unsafe information
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_EXPLAINABILITY_FIDELITY_STABILITY_CERTIFIER-01` — native scenario: measure explanation fidelity to model or system decision process
- `ELMOS_AI_EXPLAINABILITY_FIDELITY_STABILITY_CERTIFIER-02` — native scenario: test stability, sensitivity, completeness and audience comprehension
- `ELMOS_AI_EXPLAINABILITY_FIDELITY_STABILITY_CERTIFIER-03` — native scenario: verify explanation supports contestability and does not disclose unsafe information
- `ELMOS_AI_EXPLAINABILITY_FIDELITY_STABILITY_CERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_EXPLAINABILITY_FIDELITY_STABILITY_CERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
