# Implementation Guide — TargetSymphonyWorkflowGenerator

## Purpose

Generate repository-versioned workflow policy, work-item adapters, isolated workspace contracts, retry/backoff, proof-of-work and handoff artifacts for coding orchestration.

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

1. Generate versioned WORKFLOW policy
2. Generate work-item adapters and isolated workspaces
3. Generate reconciler/backoff/concurrency rules
4. Generate proof-of-work and acceptance gates
5. Run workspace loss and duplicate work recovery tests

## Native acceptance corpus

- `ELMOS_TARGET_SYMPHONY_WORKFLOW_GENERATOR-01` — WORKFLOW parse
- `ELMOS_TARGET_SYMPHONY_WORKFLOW_GENERATOR-02` — work item claim
- `ELMOS_TARGET_SYMPHONY_WORKFLOW_GENERATOR-03` — workspace isolation
- `ELMOS_TARGET_SYMPHONY_WORKFLOW_GENERATOR-04` — backoff
- `ELMOS_TARGET_SYMPHONY_WORKFLOW_GENERATOR-05` — duplicate work fencing
- `ELMOS_TARGET_SYMPHONY_WORKFLOW_GENERATOR-06` — acceptance gate
- `ELMOS_TARGET_SYMPHONY_WORKFLOW_GENERATOR-07` — workspace recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
