---
name: data-quality-profiling-reconciliation-and-rule-engine
description: Profile data, version owned quality rules, reconcile source and target, distinguish baseline defects from migration regressions, and enforce business invariants. Use for database, CDC, pipeline, lakehouse, or BI migration quality gates and cutover decisions.
---

# Data Quality and Reconciliation

## Establish the baseline

- Profile completeness, uniqueness, validity, consistency, accuracy, timeliness, integrity, conformity, distribution, and freshness.
- Record counts, nulls, distincts, ranges, quantiles, lengths, patterns, categories, outliers, keys, relationships, and freshness by approved asset scope.
- Identify rule source as constraint, business rule, data contract, BI metric, source profile, customer-approved rule, or inferred candidate.
- Give each enforceable rule an owner, severity, expression, version, and effective period.
- Never promote an inferred rule to a hard gate without approval.

## Reconcile

- Compare structure, counts by meaningful partitions, chunk or row hashes, business invariants, and distributions.
- Use full checks for critical assets; use sampling only as supplementary evidence.
- Classify defects as SOURCE_DEFECT_PRESERVED, SOURCE_DEFECT_FIXED, MIGRATION_INTRODUCED_DEFECT, or TARGET_ONLY_DEFECT.
- Record failed keys, rules, retries, resolutions, and owners while masking sensitive values.

## Decide

- Return PASS, PASS_WITH_BASELINE_DEFECTS, FAIL_MIGRATION_REGRESSION, HUMAN_REVIEW_REQUIRED, or INCONCLUSIVE.
- Block writer cutover for migration-introduced nulls, balance/inventory violations, missing critical rows, or unowned critical failures.
- Do not let row-count equality substitute for semantic or business reconciliation.
