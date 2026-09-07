# Implementation Guide — Accredited-Once Accepted-Everywhere Evidence Packager

## Purpose

Implement and independently certify accredited-once accepted-everywhere evidence packager, including assemble accreditation chain, scope, report/certificate, method, uncertainty and status evidence, generate verifier instructions for regulators and procurement teams and clearly separate internationally recognized result from local legal acceptance.

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

1. assemble accreditation chain, scope, report/certificate, method, uncertainty and status evidence
2. generate verifier instructions for regulators and procurement teams
3. clearly separate internationally recognized result from local legal acceptance
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_ACCREDITED_ONCE_ACCEPTED_EVERYWHERE_EVIDENCE_PACKAGER-01` — native scenario: assemble accreditation chain, scope, report/certificate, method, uncertainty and status evidence
- `ELMOS_ACCREDITED_ONCE_ACCEPTED_EVERYWHERE_EVIDENCE_PACKAGER-02` — native scenario: generate verifier instructions for regulators and procurement teams
- `ELMOS_ACCREDITED_ONCE_ACCEPTED_EVERYWHERE_EVIDENCE_PACKAGER-03` — native scenario: clearly separate internationally recognized result from local legal acceptance
- `ELMOS_ACCREDITED_ONCE_ACCEPTED_EVERYWHERE_EVIDENCE_PACKAGER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_ACCREDITED_ONCE_ACCEPTED_EVERYWHERE_EVIDENCE_PACKAGER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
