---
name: deterministic-repair-recipe-runner
description: "Apply a tested idempotent Batch 8 repair recipe for known imports, references, bindings, nullability, configuration, or test metadata. Use before an Agent patch."
---
# Deterministic Repair Recipe Runner
Read `../references/batch-8-repair-loop.md`. Match native code, symbol/dependency and explicit preconditions; modify only the matched generated region. Preserve rule/version, before/after hashes, invariants, expected diagnostics and validation commands.

Require fixture coverage, idempotence and rollback. Disable a recipe that adds unrelated failures or fails its postconditions. Never let a generic recipe override a verified project-specific rule.
