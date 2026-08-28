# Implementation Guide — Global Accreditation and Mutual Recognition Scope Resolver

## Purpose

Implement and independently certify global accreditation and mutual recognition scope resolver, including resolve current global, regional and national recognition arrangements and exact scopes, distinguish accredited result acceptance from product-market authorization and emit jurisdiction-specific recognition limitations and transition handling.

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

1. resolve current global, regional and national recognition arrangements and exact scopes
2. distinguish accredited result acceptance from product-market authorization
3. emit jurisdiction-specific recognition limitations and transition handling
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_GLOBAL_RECOGNITION_SCOPE_RESOLVER-01` — native scenario: resolve current global, regional and national recognition arrangements and exact scopes
- `ELMOS_GLOBAL_RECOGNITION_SCOPE_RESOLVER-02` — native scenario: distinguish accredited result acceptance from product-market authorization
- `ELMOS_GLOBAL_RECOGNITION_SCOPE_RESOLVER-03` — native scenario: emit jurisdiction-specific recognition limitations and transition handling
- `ELMOS_GLOBAL_RECOGNITION_SCOPE_RESOLVER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_GLOBAL_RECOGNITION_SCOPE_RESOLVER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
