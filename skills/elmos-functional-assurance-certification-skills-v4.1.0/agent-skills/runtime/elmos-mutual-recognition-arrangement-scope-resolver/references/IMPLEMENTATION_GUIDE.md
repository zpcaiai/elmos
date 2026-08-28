# Implementation Guide — Mutual Recognition Arrangement Scope Resolver

## Purpose

Implement and independently certify mutual recognition arrangement scope resolver, including resolve signatory, arrangement level, standard, sector, geography and effective date, verify issuer accreditation and certificate fall within recognized scope and emit accepted, conditional, unrecognized or regulator-review result.

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

1. resolve signatory, arrangement level, standard, sector, geography and effective date
2. verify issuer accreditation and certificate fall within recognized scope
3. emit accepted, conditional, unrecognized or regulator-review result
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_MUTUAL_RECOGNITION_ARRANGEMENT_SCOPE_RESOLVER-01` — native scenario: resolve signatory, arrangement level, standard, sector, geography and effective date
- `ELMOS_MUTUAL_RECOGNITION_ARRANGEMENT_SCOPE_RESOLVER-02` — native scenario: verify issuer accreditation and certificate fall within recognized scope
- `ELMOS_MUTUAL_RECOGNITION_ARRANGEMENT_SCOPE_RESOLVER-03` — native scenario: emit accepted, conditional, unrecognized or regulator-review result
- `ELMOS_MUTUAL_RECOGNITION_ARRANGEMENT_SCOPE_RESOLVER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_MUTUAL_RECOGNITION_ARRANGEMENT_SCOPE_RESOLVER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
