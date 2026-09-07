---
name: failure-attribution-and-baseline-comparator
description: "Attribute Batch 8 root causes to source-existing, migration, target environment, dependency infrastructure, test migration, flaky, mixed, or unknown origins. Use when comparing frozen baselines."
---
# Failure Attribution and Baseline Comparator
Read `../references/batch-8-repair-loop.md`. Compare source diagnostic/test evidence, target results, source-target maps, transformation history, matrix differences, dependency versions and open obligations.

Record evidence and confidence. Preserve `MIXED` when both source and migration contribute. Do not treat unexecuted source tests as passed, excuse new target failures because the source has other failures, or force an unsupported attribution.
