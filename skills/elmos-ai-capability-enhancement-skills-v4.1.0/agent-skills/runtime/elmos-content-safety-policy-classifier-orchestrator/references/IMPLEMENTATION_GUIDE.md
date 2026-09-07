# Implementation Guide — Content Safety Policy and Classifier Orchestrator

## Purpose

Compose deterministic rules, provider classifiers, custom models and human escalation under versioned safety policy and measurable error trade-offs.

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

1. compile taxonomy, thresholds and jurisdiction profile
2. route multimodal content through classifier portfolio
3. calibrate false positive/negative rates
4. apply age/tenant/context policy
5. audit appeals and classifier drift

## Native acceptance corpus

- `ELMOS_CONTENT_SAFETY_POLICY_CLASSIFIER_ORCHESTRATOR-01` — native scenario: compile taxonomy, thresholds and jurisdiction profile
- `ELMOS_CONTENT_SAFETY_POLICY_CLASSIFIER_ORCHESTRATOR-02` — native scenario: route multimodal content through classifier portfolio
- `ELMOS_CONTENT_SAFETY_POLICY_CLASSIFIER_ORCHESTRATOR-03` — native scenario: calibrate false positive/negative rates
- `ELMOS_CONTENT_SAFETY_POLICY_CLASSIFIER_ORCHESTRATOR-04` — native scenario: apply age/tenant/context policy
- `ELMOS_CONTENT_SAFETY_POLICY_CLASSIFIER_ORCHESTRATOR-05` — native scenario: audit appeals and classifier drift

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
