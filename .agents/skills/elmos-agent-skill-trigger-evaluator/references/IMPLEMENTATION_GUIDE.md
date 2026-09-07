# Implementation Guide — Agent Skill Trigger Evaluator

## Purpose

Measure whether a Skill activates for the right requests and improves task success without unacceptable false activation, latency or token overhead.

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

1. Positive, negative and adversarial trigger set governance
2. Precision/recall and confidence intervals
3. No-skill baseline and ablation comparison
4. Multi-skill conflict and precedence evaluation
5. Version-to-version trigger regression

## Native acceptance corpus

- `ELMOS_AGENT_SKILL_TRIGGER_EVALUATOR-01` — positive trigger recall
- `ELMOS_AGENT_SKILL_TRIGGER_EVALUATOR-02` — negative trigger precision
- `ELMOS_AGENT_SKILL_TRIGGER_EVALUATOR-03` — multi-skill collision
- `ELMOS_AGENT_SKILL_TRIGGER_EVALUATOR-04` — description ablation
- `ELMOS_AGENT_SKILL_TRIGGER_EVALUATOR-05` — latency/token overhead budget

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
