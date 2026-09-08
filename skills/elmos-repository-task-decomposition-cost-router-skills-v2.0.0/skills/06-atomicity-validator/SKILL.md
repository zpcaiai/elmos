---
name: elmos-atomicity-validator
version: 2.0.0
description: Validate executable leaves for semantic cohesion, safe boundaries, verification locality and handoff completeness; recommend split or merge.
---

# Atomicity Validator v2

Validate that a leaf is the smallest *safe and economical* independently executable unit, not simply a small patch.

## Inputs
- `candidate tasks`
- `granularity scores`
- `invariant ledger`
- `handoff contracts`

## Outputs
- `validated leaves`
- `split/merge recommendations`
- `atomicity exceptions`

## Procedure
1. Check one semantic objective and bounded write ownership.
2. Check local or explicitly delegated proof obligations.
3. Reject leaves that depend on hidden shared state or undocumented assumptions.
4. Split over-large leaves only at approved semantic seams.
5. Merge over-split leaves when handoff/coupling cost exceeds independent execution benefit.
6. Require owned/read/forbidden paths, scenario links, invariant links and incoming/outgoing contract IDs.
7. Allow larger units for indivisible transactions, migrations or concurrency protocols with an explicit exception reason.

## Guardrails
- `small` is neither necessary nor sufficient for atomicity.

## Acceptance criteria
- no executable leaf has unresolved hidden dependencies or critical invariant gaps

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
