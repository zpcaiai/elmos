---
name: elmos-data-migration-gate
version: 1.0.0
description: Validate schema/data migrations for forward correctness, rollback, compatibility and data integrity.
---

# Data Migration Gate

Validate schema/data migrations for forward correctness, rollback, compatibility and data integrity.

## Trigger conditions
- database/schema migration task

## Inputs
- `migration files`
- `schema`
- `fixtures`

## Outputs
- `migration evidence`
- `rollback evidence`

## Procedure
1. Test migration on representative fixture DB.
2. Verify rollback or documented irreversible strategy.
3. Check mixed-version compatibility when rolling deploys apply.
4. Validate constraints/indexes/data transformations.

## Guardrails
- Never treat successful DDL parse as sufficient.

## Acceptance criteria
- forward + integrity + rollback/irreversibility evidence complete

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
