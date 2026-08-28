# Implementation Guide — Fault Localization and Root-Cause Synthesizer

## Purpose

Correlate counterexamples, traces, diffs, changes and dependency graphs to rank root causes and bounded repair locations without becoming the correctness oracle.

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

1. cluster failures by causal signature
2. slice change and dependency graph
3. rank source/spec/adapter/runtime causes
4. propose minimal reproducer and repair boundary
5. record confidence and alternative hypotheses

## Native acceptance corpus

- `ELMOS_FAULT_LOCALIZATION_ROOT_CAUSE_SYNTHESIZER-01` — native scenario: cluster failures by causal signature
- `ELMOS_FAULT_LOCALIZATION_ROOT_CAUSE_SYNTHESIZER-02` — native scenario: slice change and dependency graph
- `ELMOS_FAULT_LOCALIZATION_ROOT_CAUSE_SYNTHESIZER-03` — native scenario: rank source/spec/adapter/runtime causes
- `ELMOS_FAULT_LOCALIZATION_ROOT_CAUSE_SYNTHESIZER-04` — native scenario: propose minimal reproducer and repair boundary
- `ELMOS_FAULT_LOCALIZATION_ROOT_CAUSE_SYNTHESIZER-05` — native scenario: record confidence and alternative hypotheses

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
