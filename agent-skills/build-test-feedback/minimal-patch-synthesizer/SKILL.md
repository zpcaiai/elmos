---
name: minimal-patch-synthesizer
description: "Synthesize the smallest structured, hash-bound, reversible patch for one Batch 8 repair plan. Use after a deterministic rule or bounded Agent selects a change."
---
# Minimal Patch Synthesizer
Read `../references/batch-8-repair-loop.md` and emit `contracts/repair-loop-schema/structured-patch.schema.json`.

Minimize files, declarations, lines, public-contract impact, dependencies and behavior. Include cluster/plan IDs, operation, before/after hashes, invariants and expected diagnostic changes. Split patches over configured limits.

Do not format unrelated code, cross manual regions, bundle public API/dependency changes, refactor opportunistically or emit a patch without an inverse/rollback path.
