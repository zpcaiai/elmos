---
name: elmos-semantic-conflict-detector
version: 2.0.0
description: Detect conflicts between independently valid patches that violate shared semantics, invariants or behavioral scenarios.
---

# Semantic Conflict Detector

Detect integration conflicts beyond textual merge conflicts.

## Inputs
- candidate patches
- task contracts
- scenario graph
- invariant ledger
- repository graph deltas

## Outputs
- `semantic conflict report`
- `affected scenarios`
- `resolution task requests`

## Procedure
1. Compare changes to shared symbols, schemas, config, data entities and side effects.
2. Detect incompatible assumptions even when git merges cleanly.
3. Re-evaluate shared invariants and edge contracts across combined patches.
4. Run targeted scenario probes on the merged state.
5. Generate a resolution task when conflicts cannot be solved mechanically.

## Acceptance criteria
- clean textual merge is never treated as sufficient integration evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
