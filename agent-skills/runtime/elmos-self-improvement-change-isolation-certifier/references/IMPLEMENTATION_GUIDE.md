# Implementation Guide — Self-Improvement Change Isolation Certifier

## Purpose

Certify that learned prompts, rules, Skills and adapters are isolated, reviewable, reversible and cannot alter their own verifier or completion authority.

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

1. separate proposal, implementation, verification and certification roles
2. freeze verifier and policy outside candidate scope
3. test authority and sandbox boundaries
4. verify rollback and evidence lineage
5. block recursive self-modification of K8

## Native acceptance corpus

- `ELMOS_SELF_IMPROVEMENT_CHANGE_ISOLATION_CERTIFIER-01` — native scenario: separate proposal, implementation, verification and certification roles
- `ELMOS_SELF_IMPROVEMENT_CHANGE_ISOLATION_CERTIFIER-02` — native scenario: freeze verifier and policy outside candidate scope
- `ELMOS_SELF_IMPROVEMENT_CHANGE_ISOLATION_CERTIFIER-03` — native scenario: test authority and sandbox boundaries
- `ELMOS_SELF_IMPROVEMENT_CHANGE_ISOLATION_CERTIFIER-04` — native scenario: verify rollback and evidence lineage
- `ELMOS_SELF_IMPROVEMENT_CHANGE_ISOLATION_CERTIFIER-05` — native scenario: block recursive self-modification of K8

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
