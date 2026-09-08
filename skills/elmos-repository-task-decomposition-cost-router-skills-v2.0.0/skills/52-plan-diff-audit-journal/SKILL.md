---
name: elmos-plan-diff-audit-journal
version: 2.0.0
description: Persist immutable plan revisions and graph diffs so decomposition decisions are explainable, replayable and resumable.
---

# Plan Diff & Audit Journal

Persist planning as a versioned artifact.

## Inputs
- plan revisions
- replan triggers
- split/merge decisions

## Outputs
- `.elmos/runs/<run_id>/plans/rev-*.json`
- `plan diff ledger`
- `decision reasons`

## Procedure
1. Assign monotonically increasing plan revision IDs.
2. Record added/removed/merged/split nodes and edges.
3. Record assumptions, confidence changes, affected evidence and budget/ETA delta.
4. Link execution records to the exact plan revision used.
5. Support replay from any stable checkpoint.

## Acceptance criteria
- current plan can be reconstructed from revision history
- no execution task lacks a plan revision reference

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
