# Implementation Guide — AI System and Model Card Generator

## Purpose

Generate evidence-backed system/model cards describing intended use, limits, evaluations, risks, data, oversight, deployment envelope and change history.

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

1. Audience-specific disclosure
2. Intended/prohibited use and limitations
3. Evaluation and risk evidence links
4. Data/model/prompt/tool inventory summary
5. Version/change and recertification state

## Native acceptance corpus

- `ELMOS_AI_SYSTEM_MODEL_CARD_GENERATOR-01` — evidence link completeness
- `ELMOS_AI_SYSTEM_MODEL_CARD_GENERATOR-02` — prohibited-use disclosure
- `ELMOS_AI_SYSTEM_MODEL_CARD_GENERATOR-03` — stale card invalidation
- `ELMOS_AI_SYSTEM_MODEL_CARD_GENERATOR-04` — audience redaction
- `ELMOS_AI_SYSTEM_MODEL_CARD_GENERATOR-05` — limitation honesty
- `ELMOS_AI_SYSTEM_MODEL_CARD_GENERATOR-06` — version change update

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
