---
name: incident-regression-learning
description: Convert every production defect, near miss and customer migration discrepancy into durable ETGB regression cases, mutants, hidden variants and planner knowledge.
---

# Incident Regression Learning

## Trigger

Invoke for a production defect, customer acceptance mismatch, security finding, corrupted data, wrong SQL result, unsupported silent success, recovery failure, billing discrepancy, evidence gap or benchmark false negative.

## Required outputs

1. Minimal deterministic L0/L1 reproduction.
2. Realistic repository/database replay when interactions matter.
3. Independent Oracle and first difference.
4. Hidden variant that avoids literal overfitting.
5. Domain mutant reproducing the faulty behavior.
6. Failure-cluster signature and root-cause link.
7. Affected capability/matrix cell and risk-planner mapping.
8. Fixed candidate digest and proof that the old candidate fails/new candidate passes.

## Workflow

Preserve incident evidence, redact sensitive data, classify source/product/Oracle/infrastructure cause, minimize without erasing the defect, add boundary/concurrent/fault variants, run mutation and multi-seed checks, then materialize the stable case. Do not close an incident solely because a Prompt was manually changed once.

## Planner feedback

If the incident was not selected in PR testing, add dependency/capability mapping and a selector regression. If public benchmark memorization contributed, add a private/time-split variant. If the Oracle was wrong, version the Oracle and reassess affected historical evidence.

## Lifecycle

Track first/last seen, occurrence count, affected candidates, owner and status. Retain old case versions so historical release decisions remain interpretable. Retire only when superseded by stronger coverage and preserve lineage.

## Gate

A P0 incident fix cannot be promoted until its minimal, realistic and hidden regressions pass and the representative mutant is killed.
