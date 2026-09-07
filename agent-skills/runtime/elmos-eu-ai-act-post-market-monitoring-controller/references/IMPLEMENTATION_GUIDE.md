# Implementation Guide — EU AI Act Post-Market Monitoring Controller

## Purpose

Generate risk-based post-market monitoring, logging, feedback, incident, corrective action and evidence workflows for applicable AI systems.

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

1. compile applicable monitoring plan and metrics
2. collect performance, risk and complaint signals
3. triage serious and systemic issues
4. manage corrective action and change control
5. produce reviewable evidence and unresolved legal decisions

## Native acceptance corpus

- `ELMOS_EU_AI_ACT_POST_MARKET_MONITORING_CONTROLLER-01` — native scenario: compile applicable monitoring plan and metrics
- `ELMOS_EU_AI_ACT_POST_MARKET_MONITORING_CONTROLLER-02` — native scenario: collect performance, risk and complaint signals
- `ELMOS_EU_AI_ACT_POST_MARKET_MONITORING_CONTROLLER-03` — native scenario: triage serious and systemic issues
- `ELMOS_EU_AI_ACT_POST_MARKET_MONITORING_CONTROLLER-04` — native scenario: manage corrective action and change control
- `ELMOS_EU_AI_ACT_POST_MARKET_MONITORING_CONTROLLER-05` — native scenario: produce reviewable evidence and unresolved legal decisions

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
