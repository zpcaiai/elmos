# Implementation Guide — Sector Assurance Profile Applicability and Tailoring Governor

## Purpose

Implement and independently certify sector assurance profile applicability and tailoring governor, including determine applicable sector standards, regulators, product classification and lifecycle stage, tailor controls only with documented rationale and compensating evidence and manage conflicts, precedence, effective dates and external expert approval.

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

1. determine applicable sector standards, regulators, product classification and lifecycle stage
2. tailor controls only with documented rationale and compensating evidence
3. manage conflicts, precedence, effective dates and external expert approval
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_SECTOR_PROFILE_APPLICABILITY_TAILORING_GOVERNOR-01` — native scenario: determine applicable sector standards, regulators, product classification and lifecycle stage
- `ELMOS_SECTOR_PROFILE_APPLICABILITY_TAILORING_GOVERNOR-02` — native scenario: tailor controls only with documented rationale and compensating evidence
- `ELMOS_SECTOR_PROFILE_APPLICABILITY_TAILORING_GOVERNOR-03` — native scenario: manage conflicts, precedence, effective dates and external expert approval
- `ELMOS_SECTOR_PROFILE_APPLICABILITY_TAILORING_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_SECTOR_PROFILE_APPLICABILITY_TAILORING_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
