# Implementation Guide — Counterfactual Fairness and Causal Stability Verifier

## Purpose

Implement and independently certify counterfactual fairness and causal stability verifier, including build causal assumptions and test counterfactual invariance where justified, distinguish legitimate mediators from prohibited proxies and stress causal stability across environments and policy changes.

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

1. build causal assumptions and test counterfactual invariance where justified
2. distinguish legitimate mediators from prohibited proxies
3. stress causal stability across environments and policy changes
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_COUNTERFACTUAL_FAIRNESS_CAUSAL_STABILITY_VERIFIER-01` — native scenario: build causal assumptions and test counterfactual invariance where justified
- `ELMOS_AI_COUNTERFACTUAL_FAIRNESS_CAUSAL_STABILITY_VERIFIER-02` — native scenario: distinguish legitimate mediators from prohibited proxies
- `ELMOS_AI_COUNTERFACTUAL_FAIRNESS_CAUSAL_STABILITY_VERIFIER-03` — native scenario: stress causal stability across environments and policy changes
- `ELMOS_AI_COUNTERFACTUAL_FAIRNESS_CAUSAL_STABILITY_VERIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_COUNTERFACTUAL_FAIRNESS_CAUSAL_STABILITY_VERIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
