---
name: migration-wave-planner
description: Group a migration DAG into bounded ELMOS execution waves. Use for parallelism, dependency-aware sequencing, exit criteria or staged modernization delivery.
---
# Migration Wave Planner

## Workflow
1. Derive waves only from a validated DAG.
2. Respect organization maximum parallel steps and sensitive-step gates.
3. Give every wave explicit required evidence and exit criterion.
4. Preserve deterministic order for equal-rank steps.

## Acceptance
- No child appears before its parent.
- Wave width never exceeds policy.
- Failed or missing exit evidence blocks later waves.

