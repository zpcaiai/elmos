# Implementation Guide — Confidential AI Inference Receipt Certifier

## Purpose

Implement and independently certify confidential ai inference receipt certifier, including issue signed receipt binding model, code, policy, input commitment, output commitment and trusted execution evidence, prove inference occurred in approved confidential environment without exposing protected content and verify receipt replay, privacy and cross-provider portability.

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

1. issue signed receipt binding model, code, policy, input commitment, output commitment and trusted execution evidence
2. prove inference occurred in approved confidential environment without exposing protected content
3. verify receipt replay, privacy and cross-provider portability
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CONFIDENTIAL_AI_INFERENCE_RECEIPT_CERTIFIER-01` — native scenario: issue signed receipt binding model, code, policy, input commitment, output commitment and trusted execution evidence
- `ELMOS_CONFIDENTIAL_AI_INFERENCE_RECEIPT_CERTIFIER-02` — native scenario: prove inference occurred in approved confidential environment without exposing protected content
- `ELMOS_CONFIDENTIAL_AI_INFERENCE_RECEIPT_CERTIFIER-03` — native scenario: verify receipt replay, privacy and cross-provider portability
- `ELMOS_CONFIDENTIAL_AI_INFERENCE_RECEIPT_CERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CONFIDENTIAL_AI_INFERENCE_RECEIPT_CERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
