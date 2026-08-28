# Implementation Guide — Cross-Border Certificate Acceptance Planner

## Purpose

Implement and independently certify cross-border certificate acceptance planner, including combine mutual recognition, local regulation, market authorization and customer contract, identify supplemental tests, translations, local representatives and data restrictions and produce jurisdiction-specific acceptance dossier without legal overclaim.

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

1. combine mutual recognition, local regulation, market authorization and customer contract
2. identify supplemental tests, translations, local representatives and data restrictions
3. produce jurisdiction-specific acceptance dossier without legal overclaim
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CERTIFICATE_CROSS_BORDER_JURISDICTION_ACCEPTANCE_PLANNER-01` — native scenario: combine mutual recognition, local regulation, market authorization and customer contract
- `ELMOS_CERTIFICATE_CROSS_BORDER_JURISDICTION_ACCEPTANCE_PLANNER-02` — native scenario: identify supplemental tests, translations, local representatives and data restrictions
- `ELMOS_CERTIFICATE_CROSS_BORDER_JURISDICTION_ACCEPTANCE_PLANNER-03` — native scenario: produce jurisdiction-specific acceptance dossier without legal overclaim
- `ELMOS_CERTIFICATE_CROSS_BORDER_JURISDICTION_ACCEPTANCE_PLANNER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CERTIFICATE_CROSS_BORDER_JURISDICTION_ACCEPTANCE_PLANNER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
