# Implementation Guide — Certification Body Financial and Liability Risk Governor

## Purpose

Implement and independently certify certification body financial and liability risk governor, including assess financial stability, liability, insurance and revenue concentration threats to impartial operation, separate sales incentives from technical decisions and maintain contingency for certificate records, appeals and surveillance continuity.

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

1. assess financial stability, liability, insurance and revenue concentration threats to impartial operation
2. separate sales incentives from technical decisions
3. maintain contingency for certificate records, appeals and surveillance continuity
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CERTIFICATION_BODY_FINANCIAL_LIABILITY_RISK_GOVERNOR-01` — native scenario: assess financial stability, liability, insurance and revenue concentration threats to impartial operation
- `ELMOS_CERTIFICATION_BODY_FINANCIAL_LIABILITY_RISK_GOVERNOR-02` — native scenario: separate sales incentives from technical decisions
- `ELMOS_CERTIFICATION_BODY_FINANCIAL_LIABILITY_RISK_GOVERNOR-03` — native scenario: maintain contingency for certificate records, appeals and surveillance continuity
- `ELMOS_CERTIFICATION_BODY_FINANCIAL_LIABILITY_RISK_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CERTIFICATION_BODY_FINANCIAL_LIABILITY_RISK_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
