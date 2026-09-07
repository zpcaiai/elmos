---
name: batch-8-conformance-and-gate-controller
description: "Evaluate per-module Batch 8 R-A through R-E gates for build, static semantics, tests, repair quality, reproducibility, and traceability. Use before admitting a target module to Batch 9."
---
# Batch 8 Conformance and Gate Controller
Read `../references/batch-8-repair-loop.md` and validate `contracts/repair-loop-schema/batch-8-conformance-report.schema.json`.

Score dependency restore, build load, compile, symbol/type validation, discovery, migrated/required tests, unit/contract/integration pass, flaky rate, repair provenance, regression classes, obligations and trace coverage per module. Exclude source-existing failures and quarantined tests from migration/stable pass rates.

Block zero-test false green, silent public/security/transaction/serialization drift, deleted/weakened tests, unreviewed high-risk Agent output, suppression/dynamic growth, missing rollback, oscillation, unclassified failures and missing full clean regression. R-D admits Batch 9 only; it does not prove production readiness.
