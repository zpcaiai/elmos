---
name: behavioral-difference-root-cause-classifier
description: "Classify and cluster Batch 9 differences by evidenced semantic root cause. Use to connect diffs to mappings, lowering, framework recipes, dependencies, configuration, time, data or collectors."
---

# Behavioral Difference Root Cause Classifier

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Correlate field diffs with source-target maps, UIR, transformation history, traces and recent patches.
2. Cluster multiple surface failures under one supported primary cause.
3. Keep source bug and unknown classifications evidence-bound.

## Hard rules

- Do not force an unknown into a convenient category.
- Keep security findings high severity.
- Do not modify normalization based only on a classification.

## Output

Emit stable clusters and bounded Batch 8 repair candidates.

