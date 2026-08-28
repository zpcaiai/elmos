# Implementation Guide — Third-Party Mark of Conformity License Governor

## Purpose

Implement and independently certify third-party mark of conformity license governor, including issue mark license with exact scope, artwork, placement and surveillance conditions, monitor digital and physical usage across products and marketing and automate correction, suspension and revocation enforcement.

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

1. issue mark license with exact scope, artwork, placement and surveillance conditions
2. monitor digital and physical usage across products and marketing
3. automate correction, suspension and revocation enforcement
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_THIRD_PARTY_MARK_CONFORMITY_LICENSE_GOVERNOR-01` — native scenario: issue mark license with exact scope, artwork, placement and surveillance conditions
- `ELMOS_THIRD_PARTY_MARK_CONFORMITY_LICENSE_GOVERNOR-02` — native scenario: monitor digital and physical usage across products and marketing
- `ELMOS_THIRD_PARTY_MARK_CONFORMITY_LICENSE_GOVERNOR-03` — native scenario: automate correction, suspension and revocation enforcement
- `ELMOS_THIRD_PARTY_MARK_CONFORMITY_LICENSE_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_THIRD_PARTY_MARK_CONFORMITY_LICENSE_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
