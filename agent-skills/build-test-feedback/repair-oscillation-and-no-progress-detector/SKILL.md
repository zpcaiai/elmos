---
name: repair-oscillation-and-no-progress-detector
description: "Detect repeated patches, Snapshot/diagnostic cycles, rule conflicts, and bounded windows without Batch 8 progress. Use between repair rounds."
---
# Repair Oscillation and No Progress Detector
Read `../references/batch-8-repair-loop.md`. Track patch ID/content, Snapshot, diagnostic set, blocking count, test pass rate, rule and dependency version. Detect A-to-B-to-A changes and three-round non-improvement.

Freeze the conflicting strategy/rule, restore the last stable Snapshot and escalate with full attempt history. Do not hide no progress with more retries or cosmetic prompt changes.
