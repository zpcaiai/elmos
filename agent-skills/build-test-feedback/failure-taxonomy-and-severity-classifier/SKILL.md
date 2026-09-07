---
name: failure-taxonomy-and-severity-classifier
description: "Classify normalized Batch 8 diagnostics by actionable category, severity, priority, and confidence. Use before clustering or selecting any repair strategy."
---
# Failure Taxonomy and Severity Classifier
Read `../references/batch-8-repair-loop.md`. Assign the documented primary category and a precise subtype when evidence supports it. Rank security/data-destruction as P0, build/critical-contract blockers as P1, ordinary failures as P2 and nonblocking quality/style below them.

Keep `UNKNOWN` for insufficient evidence. Route environment failures away from code Agents. Do not mark a source-baseline failure as migration-introduced or auto-close a low-confidence blocking classification.
