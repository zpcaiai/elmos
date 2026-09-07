# Implementation Guide — Certification Document and Record Control Governor

## Purpose

Implement and independently certify certification document and record control governor, including control approval, issue, revision, access, retention, legal hold and disposition, distinguish normative controlled documents from informative guidance and preserve audit trail and superseded versions needed to reproduce decisions.

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

1. control approval, issue, revision, access, retention, legal hold and disposition
2. distinguish normative controlled documents from informative guidance
3. preserve audit trail and superseded versions needed to reproduce decisions
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_DOCUMENT_RECORD_CONTROL_CERTIFICATION_GOVERNOR-01` — native scenario: control approval, issue, revision, access, retention, legal hold and disposition
- `ELMOS_DOCUMENT_RECORD_CONTROL_CERTIFICATION_GOVERNOR-02` — native scenario: distinguish normative controlled documents from informative guidance
- `ELMOS_DOCUMENT_RECORD_CONTROL_CERTIFICATION_GOVERNOR-03` — native scenario: preserve audit trail and superseded versions needed to reproduce decisions
- `ELMOS_DOCUMENT_RECORD_CONTROL_CERTIFICATION_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_DOCUMENT_RECORD_CONTROL_CERTIFICATION_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
