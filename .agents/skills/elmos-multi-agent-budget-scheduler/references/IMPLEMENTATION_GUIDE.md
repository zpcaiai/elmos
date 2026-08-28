# Implementation Guide — Multi-Agent Budget Scheduler

## Purpose

Allocate model, tool, latency, fanout and cost budgets across agent teams using priority, uncertainty, critical path and verified task-fit.

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

1. Per-agent and shared budget envelopes
2. Critical-path and slack-aware scheduling
3. Dynamic reallocation under uncertainty
4. Priority/fairness and tenant quota
5. Budget-aware stop and degraded mode

## Native acceptance corpus

- `ELMOS_MULTI_AGENT_BUDGET_SCHEDULER-01` — critical path allocation
- `ELMOS_MULTI_AGENT_BUDGET_SCHEDULER-02` — fanout cap
- `ELMOS_MULTI_AGENT_BUDGET_SCHEDULER-03` — budget reallocation
- `ELMOS_MULTI_AGENT_BUDGET_SCHEDULER-04` — tenant fairness
- `ELMOS_MULTI_AGENT_BUDGET_SCHEDULER-05` — degraded mode
- `ELMOS_MULTI_AGENT_BUDGET_SCHEDULER-06` — hard cost stop

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
