---
name: repair-strategy-planner
description: "Select a minimal, low-risk, verifiable repair strategy for one Batch 8 root-cause cluster. Use after attribution and impact analysis."
---
# Repair Strategy Planner
Read `../references/batch-8-repair-loop.md` and emit `contracts/repair-loop-schema/repair-plan.schema.json`.

Prefer environment correction, deterministic configuration/code recipe, mapping correction, adapter/regeneration, bounded Agent patch and finally human handling. Bind the plan to one cluster, allowed files/declarations, locked invariants, validations and rollback Snapshot.

Never choose test deletion, assertion weakening, global suppression, `any`/`dynamic`, exception swallowing, authorization removal, fixed returns, async-to-sync conversion or unbounded dependency upgrades.
