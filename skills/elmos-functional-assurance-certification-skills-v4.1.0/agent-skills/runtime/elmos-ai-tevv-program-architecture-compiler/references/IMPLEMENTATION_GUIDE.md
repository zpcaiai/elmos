# Implementation Guide — AI TEVV Program Architecture Compiler

## Purpose

Implement and independently certify ai tevv program architecture compiler, including compile context, stakeholders, claims, metrics, test levels and evidence into an end-to-end TEVV program, separate technical performance, sociotechnical impact and operational outcome evaluation and define independent challenge, holdout, monitoring and recertification phases.

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

1. compile context, stakeholders, claims, metrics, test levels and evidence into an end-to-end TEVV program
2. separate technical performance, sociotechnical impact and operational outcome evaluation
3. define independent challenge, holdout, monitoring and recertification phases
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_TEVV_PROGRAM_ARCHITECTURE_COMPILER-01` — native scenario: compile context, stakeholders, claims, metrics, test levels and evidence into an end-to-end TEVV program
- `ELMOS_AI_TEVV_PROGRAM_ARCHITECTURE_COMPILER-02` — native scenario: separate technical performance, sociotechnical impact and operational outcome evaluation
- `ELMOS_AI_TEVV_PROGRAM_ARCHITECTURE_COMPILER-03` — native scenario: define independent challenge, holdout, monitoring and recertification phases
- `ELMOS_AI_TEVV_PROGRAM_ARCHITECTURE_COMPILER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_TEVV_PROGRAM_ARCHITECTURE_COMPILER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
