# Implementation Guide — Deterministic Model and Tool Record/Replay Harness

## Purpose

Capture normalized model, tool, retrieval, clock, randomness and external observations for deterministic debugging and bounded regression replay.

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

1. record exact request/response envelopes and digests
2. virtualize time, randomness and nondeterministic IDs
3. replay tools with side effects suppressed or reconciled
4. compare causal trace and terminal state
5. redact/encrypt sensitive payloads by policy

## Native acceptance corpus

- `ELMOS_DETERMINISTIC_RECORD_REPLAY_MODEL_TOOL_HARNESS-01` — native scenario: record exact request/response envelopes and digests
- `ELMOS_DETERMINISTIC_RECORD_REPLAY_MODEL_TOOL_HARNESS-02` — native scenario: virtualize time, randomness and nondeterministic IDs
- `ELMOS_DETERMINISTIC_RECORD_REPLAY_MODEL_TOOL_HARNESS-03` — native scenario: replay tools with side effects suppressed or reconciled
- `ELMOS_DETERMINISTIC_RECORD_REPLAY_MODEL_TOOL_HARNESS-04` — native scenario: compare causal trace and terminal state
- `ELMOS_DETERMINISTIC_RECORD_REPLAY_MODEL_TOOL_HARNESS-05` — native scenario: redact/encrypt sensitive payloads by policy

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
