# Implementation Guide — Explainability, Decision and Recourse Generator

## Purpose

Generate bounded explanations, evidence links, uncertainty, counterfactuals and appeal/recourse paths for AI-assisted decisions.

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

1. classify decision and explanation audience
2. trace inputs, policies, tools and evidence
3. generate faithful bounded explanation
4. offer authorized correction and appeal paths
5. test consistency, privacy and non-deception

## Native acceptance corpus

- `ELMOS_EXPLAINABILITY_DECISION_RECOURSE_GENERATOR-01` — native scenario: classify decision and explanation audience
- `ELMOS_EXPLAINABILITY_DECISION_RECOURSE_GENERATOR-02` — native scenario: trace inputs, policies, tools and evidence
- `ELMOS_EXPLAINABILITY_DECISION_RECOURSE_GENERATOR-03` — native scenario: generate faithful bounded explanation
- `ELMOS_EXPLAINABILITY_DECISION_RECOURSE_GENERATOR-04` — native scenario: offer authorized correction and appeal paths
- `ELMOS_EXPLAINABILITY_DECISION_RECOURSE_GENERATOR-05` — native scenario: test consistency, privacy and non-deception

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
