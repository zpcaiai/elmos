# Implementation Guide — AI Policy-as-Code Compiler

## Purpose

Compile governance and security decisions into versioned Rego or equivalent policies with tests, simulation, staged rollout and explanation artifacts.

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

1. Typed policy input/output model
2. Deterministic compilation to policy engine
3. Positive/negative/unknown tests
4. Shadow and staged policy rollout
5. Decision explanation and rollback

## Native acceptance corpus

- `ELMOS_AI_POLICY_AS_CODE_COMPILER-01` — allow case
- `ELMOS_AI_POLICY_AS_CODE_COMPILER-02` — deny case
- `ELMOS_AI_POLICY_AS_CODE_COMPILER-03` — unknown default deny
- `ELMOS_AI_POLICY_AS_CODE_COMPILER-04` — conflict resolution
- `ELMOS_AI_POLICY_AS_CODE_COMPILER-05` — shadow comparison
- `ELMOS_AI_POLICY_AS_CODE_COMPILER-06` — rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
