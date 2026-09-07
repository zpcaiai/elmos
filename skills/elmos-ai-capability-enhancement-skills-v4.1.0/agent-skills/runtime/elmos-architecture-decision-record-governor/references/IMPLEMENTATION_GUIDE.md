# Implementation Guide — Architecture Decision Record Governor

## Purpose

Create, link, supersede and validate ADRs against requirements, evidence, implementation and operational outcomes.

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

1. generate decision context and alternatives
2. link claims to evidence and assumptions
3. track implementation and supersession
4. detect code/config divergence from decision
5. measure outcome and trigger review

## Native acceptance corpus

- `ELMOS_ARCHITECTURE_DECISION_RECORD_GOVERNOR-01` — native scenario: generate decision context and alternatives
- `ELMOS_ARCHITECTURE_DECISION_RECORD_GOVERNOR-02` — native scenario: link claims to evidence and assumptions
- `ELMOS_ARCHITECTURE_DECISION_RECORD_GOVERNOR-03` — native scenario: track implementation and supersession
- `ELMOS_ARCHITECTURE_DECISION_RECORD_GOVERNOR-04` — native scenario: detect code/config divergence from decision
- `ELMOS_ARCHITECTURE_DECISION_RECORD_GOVERNOR-05` — native scenario: measure outcome and trigger review

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
