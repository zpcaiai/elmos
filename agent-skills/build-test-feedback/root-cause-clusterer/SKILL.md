---
name: root-cause-clusterer
description: "Cluster many Batch 8 diagnostics into causal, independently repairable root-cause units. Use after diagnostic normalization and taxonomy classification."
---
# Root Cause Clusterer
Read `../references/batch-8-repair-loop.md` and emit `contracts/repair-loop-schema/diagnostic-cluster.schema.json` records.

Use native code, missing package/symbol, upstream module, declaration, first failing phase, mapping rule and causal dependency. Choose one primary cluster for each Diagnostic while preserving alternate links and history.

Do not merge on similar wording alone, merge unrelated same-named symbols, or combine security findings with style issues. Produce one primary repair scope per cluster.
