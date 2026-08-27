---
name: risk-based-test-selection
description: Select immutable ETGB plans using change impact, P0 obligations, historical failures, coverage gaps, uncertainty, scale and randomized unaffected controls.
---

# Risk-Based Test Selection

## Goal

Reduce PR and continuous-evaluation cost without creating blind spots. Selection is evidence-driven and immutable after the plan digest is published.

## Inputs

- changed files, dependency graph and semantic capability map;
- candidate components and digests;
- case matrix, priority and repository scale;
- historical failures/incidents and flaky cases;
- model uncertainty or low-confidence adaptation cells;
- recent coverage and mutation survivors;
- budget and target profile.

## Selection policy

Always include smoke. Include every affected P0 case and linked incident regression. Rank remaining cases by priority, repository level, changed business line, past failures, uncertainty, security/transaction sensitivity and uncovered capability. Reserve a deterministic random sample of unaffected controls to detect impact-map false negatives.

Do not let a maximum-case limit remove mandatory affected P0 cases. When Git diff, dependency graph or mapping is unavailable, fail safe to a broader plan and record the fallback.

## Plan integrity

Persist selected IDs, rationale, seed, change set, candidate digest, selection-policy version and stable shards. Compute `plan_digest` over all material fields. Workers execute the frozen case IDs; they cannot dynamically remove failing cases or add favorable replacements.

## Validation of the selector

Test the selector itself with synthetic changes, historical incidents and deliberately hidden dependencies. Track false-negative and false-positive rate, random-control discoveries, cost saved and P0 recall. A production incident caused by an omitted case becomes a permanent planner regression.

## Implementation

Use `etgb/risk.py`, `etgb/planner.py` and `etgb plan`. The plan schema is `schemas/run-plan.schema.json`.

## Release rule

Release/golden profiles remain full declared scope. Risk-based pruning is primarily for PR/nightly scheduling and cannot waive a required release cell.
