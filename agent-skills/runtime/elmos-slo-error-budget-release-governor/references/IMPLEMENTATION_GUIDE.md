# Implementation Guide — SLO and Error Budget Release Governor

## Purpose

Govern release and promotion decisions using service-level objectives, error budgets, quality/cost objectives, burn rates and customer commitments.

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

1. Compile measurable SLI/SLO and windows
2. Track fast/slow burn and data completeness
3. Separate external dependency and internal responsibility
4. Block risky release when budget policy requires
5. Record authorized exception and customer impact

## Native acceptance corpus

- `ELMOS_SLO_ERROR_BUDGET_RELEASE_GOVERNOR-01` — availability SLO
- `ELMOS_SLO_ERROR_BUDGET_RELEASE_GOVERNOR-02` — latency SLO
- `ELMOS_SLO_ERROR_BUDGET_RELEASE_GOVERNOR-03` — correctness/grounding SLO
- `ELMOS_SLO_ERROR_BUDGET_RELEASE_GOVERNOR-04` — cost budget
- `ELMOS_SLO_ERROR_BUDGET_RELEASE_GOVERNOR-05` — fast burn block
- `ELMOS_SLO_ERROR_BUDGET_RELEASE_GOVERNOR-06` — missing telemetry block
- `ELMOS_SLO_ERROR_BUDGET_RELEASE_GOVERNOR-07` — release after recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
