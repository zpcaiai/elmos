---
name: budget-cost-eta-governance
description: Reserve and reconcile tokens, credits, compute and machine wall-clock; enforce budgets in real time and produce evidence-backed ETAs for Elmos runs.
---

# Budget, Cost and Machine ETA Governance

## Scope

Govern prepaid token/credit consumption, model-provider usage, compute/storage/network cost and Elmos machine wall-clock. Do not convert these figures into human person-days unless a separate business analysis explicitly asks for it.

## Before execution

- estimate p50/p90 machine ETA from capability/pair/stack/scale history;
- estimate input/output tokens and credits;
- reserve maximum budgets atomically against the account;
- verify the account's three-concurrent-task limit and tenant quota;
- persist estimation model/version and confidence basis.

## During execution

Every phase posts usage with an idempotency key. Repeated provider callbacks or retries return the original ledger event. Track reserved, consumed and remaining input tokens, output tokens, credits and wall-clock. Emit threshold events at configurable ratios.

Recommended actions:

- 70%: warn and refresh ETA;
- 90%: checkpoint and require policy decision for optional work;
- 100%: stop at a safe point unless an explicit overage policy exists.

Critical validation and compensation may use a separately bounded emergency reserve; they may not silently overspend the customer's balance.

## ETA

ETA must be based on comparable historical cases and current concurrency. Report p50 and p90, sample count, fallback share, queue delay separately, and update after each phase. Alert on systematic underestimation and retrain/calibrate the estimator.

## Close and reconcile

On completion, failure or cancellation, sum idempotent ledger events, compare with recorded totals and provider statements, release unused reservation, persist actual machine wall-clock and expose cost by phase, case, model and business line.

## Implementation

Use `etgb/budget.py`, PostgreSQL budget/usage tables, `etgb eta`, and the budget events in AsyncAPI.

## Hard gates

Negative credit, duplicate billing, unbounded retry cost, missing usage evidence, unreconciled cancellation or continued optional work after hard exhaustion blocks release/production certification.
