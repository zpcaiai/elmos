# Implementation Guide — Conformity Assessment Impartiality Risk Governor

## Purpose

Implement and independently certify conformity assessment impartiality risk governor, including maintain financial, organizational, personal, model-provider and customer conflict-of-interest register, score impartiality threats and required safeguards before assignment and operate independent impartiality committee review for systemic conflicts.

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

1. maintain financial, organizational, personal, model-provider and customer conflict-of-interest register
2. score impartiality threats and required safeguards before assignment
3. operate independent impartiality committee review for systemic conflicts
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CONFORMITY_ASSESSMENT_IMPARTIALITY_RISK_GOVERNOR-01` — native scenario: maintain financial, organizational, personal, model-provider and customer conflict-of-interest register
- `ELMOS_CONFORMITY_ASSESSMENT_IMPARTIALITY_RISK_GOVERNOR-02` — native scenario: score impartiality threats and required safeguards before assignment
- `ELMOS_CONFORMITY_ASSESSMENT_IMPARTIALITY_RISK_GOVERNOR-03` — native scenario: operate independent impartiality committee review for systemic conflicts
- `ELMOS_CONFORMITY_ASSESSMENT_IMPARTIALITY_RISK_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CONFORMITY_ASSESSMENT_IMPARTIALITY_RISK_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
