# Implementation Guide — Coverage-to-Semantic-Obligation Mapper

## Purpose

Map line, branch, mutation, state, protocol, data, security and scenario coverage to Proof Obligations instead of optimizing a single percentage.

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

1. link tests to semantic subjects and claims
2. measure state/transition and boundary coverage
3. track mutation and negative-security coverage
4. identify unobservable or untestable obligations
5. prevent duplicate tests inflating closure

## Native acceptance corpus

- `ELMOS_COVERAGE_SEMANTIC_OBLIGATION_MAPPER-01` — native scenario: link tests to semantic subjects and claims
- `ELMOS_COVERAGE_SEMANTIC_OBLIGATION_MAPPER-02` — native scenario: measure state/transition and boundary coverage
- `ELMOS_COVERAGE_SEMANTIC_OBLIGATION_MAPPER-03` — native scenario: track mutation and negative-security coverage
- `ELMOS_COVERAGE_SEMANTIC_OBLIGATION_MAPPER-04` — native scenario: identify unobservable or untestable obligations
- `ELMOS_COVERAGE_SEMANTIC_OBLIGATION_MAPPER-05` — native scenario: prevent duplicate tests inflating closure

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
