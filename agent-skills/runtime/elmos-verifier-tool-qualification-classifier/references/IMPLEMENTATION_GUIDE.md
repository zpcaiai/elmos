# Implementation Guide — Verifier Tool Qualification Classifier

## Purpose

Implement and independently certify verifier tool qualification classifier, including classify tools by potential to introduce or fail to detect errors and by verification credit claimed, derive qualification level, operational requirements and independent checks and prevent unqualified generators, analyzers or LLM judges from reducing assurance obligations.

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

1. classify tools by potential to introduce or fail to detect errors and by verification credit claimed
2. derive qualification level, operational requirements and independent checks
3. prevent unqualified generators, analyzers or LLM judges from reducing assurance obligations
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_VERIFIER_TOOL_QUALIFICATION_CLASSIFIER-01` — native scenario: classify tools by potential to introduce or fail to detect errors and by verification credit claimed
- `ELMOS_VERIFIER_TOOL_QUALIFICATION_CLASSIFIER-02` — native scenario: derive qualification level, operational requirements and independent checks
- `ELMOS_VERIFIER_TOOL_QUALIFICATION_CLASSIFIER-03` — native scenario: prevent unqualified generators, analyzers or LLM judges from reducing assurance obligations
- `ELMOS_VERIFIER_TOOL_QUALIFICATION_CLASSIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_VERIFIER_TOOL_QUALIFICATION_CLASSIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
