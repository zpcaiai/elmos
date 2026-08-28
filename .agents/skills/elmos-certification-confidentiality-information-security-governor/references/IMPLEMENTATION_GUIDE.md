# Implementation Guide — Certification Confidentiality and Information Security Governor

## Purpose

Implement and independently certify certification confidentiality and information security governor, including classify applicant, test, vulnerability, appeal and personnel information, enforce need-to-know, secure transfer, clean-room use and disclosure authorization and balance confidentiality with public certificate and incident obligations.

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

1. classify applicant, test, vulnerability, appeal and personnel information
2. enforce need-to-know, secure transfer, clean-room use and disclosure authorization
3. balance confidentiality with public certificate and incident obligations
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CERTIFICATION_CONFIDENTIALITY_INFORMATION_SECURITY_GOVERNOR-01` — native scenario: classify applicant, test, vulnerability, appeal and personnel information
- `ELMOS_CERTIFICATION_CONFIDENTIALITY_INFORMATION_SECURITY_GOVERNOR-02` — native scenario: enforce need-to-know, secure transfer, clean-room use and disclosure authorization
- `ELMOS_CERTIFICATION_CONFIDENTIALITY_INFORMATION_SECURITY_GOVERNOR-03` — native scenario: balance confidentiality with public certificate and incident obligations
- `ELMOS_CERTIFICATION_CONFIDENTIALITY_INFORMATION_SECURITY_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CERTIFICATION_CONFIDENTIALITY_INFORMATION_SECURITY_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
