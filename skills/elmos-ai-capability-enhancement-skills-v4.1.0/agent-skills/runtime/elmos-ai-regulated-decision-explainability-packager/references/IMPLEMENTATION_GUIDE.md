# Implementation Guide — AI Regulated Decision Explainability Packager

## Purpose

Package decision inputs, evidence, rules, model contribution, uncertainty, oversight and appeal artifacts for regulated or high-impact decisions.

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

1. Decision context and data lineage
2. Rule/model/tool contribution record
3. Uncertainty and limitation disclosure
4. Human oversight and approval trail
5. Contestability, appeal and correction workflow

## Native acceptance corpus

- `ELMOS_AI_REGULATED_DECISION_EXPLAINABILITY_PACKAGER-01` — complete decision record
- `ELMOS_AI_REGULATED_DECISION_EXPLAINABILITY_PACKAGER-02` — missing evidence block
- `ELMOS_AI_REGULATED_DECISION_EXPLAINABILITY_PACKAGER-03` — uncertainty display
- `ELMOS_AI_REGULATED_DECISION_EXPLAINABILITY_PACKAGER-04` — human override
- `ELMOS_AI_REGULATED_DECISION_EXPLAINABILITY_PACKAGER-05` — appeal replay
- `ELMOS_AI_REGULATED_DECISION_EXPLAINABILITY_PACKAGER-06` — data correction propagation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
