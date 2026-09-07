# Implementation Guide — Cross-Scheme Claim Mapping and Equivalence Verifier

## Purpose

Implement and independently certify cross-scheme claim mapping and equivalence verifier, including map claims, assurance levels, scopes and decision rules between certification schemes, prove exact, stronger, weaker, overlapping or incomparable relationships and prevent semantic loss during certificate translation.

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

1. map claims, assurance levels, scopes and decision rules between certification schemes
2. prove exact, stronger, weaker, overlapping or incomparable relationships
3. prevent semantic loss during certificate translation
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CROSS_SCHEME_CLAIM_MAPPING_EQUIVALENCE_VERIFIER-01` — native scenario: map claims, assurance levels, scopes and decision rules between certification schemes
- `ELMOS_CROSS_SCHEME_CLAIM_MAPPING_EQUIVALENCE_VERIFIER-02` — native scenario: prove exact, stronger, weaker, overlapping or incomparable relationships
- `ELMOS_CROSS_SCHEME_CLAIM_MAPPING_EQUIVALENCE_VERIFIER-03` — native scenario: prevent semantic loss during certificate translation
- `ELMOS_CROSS_SCHEME_CLAIM_MAPPING_EQUIVALENCE_VERIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CROSS_SCHEME_CLAIM_MAPPING_EQUIVALENCE_VERIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
