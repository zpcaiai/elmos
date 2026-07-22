---
name: crash-restart-and-crash-consistency-validator
description: "Use when Batch 10 must validate restart, in-flight work, durable state and crash consistency."
---

# Crash Restart And Crash Consistency Validator

Read `../references/batch-10-production-hardening.md` completely before acting. Use `modules/production-hardening` for gate semantics and validate machine artifacts against `contracts/production-hardening-schema`.

## Required inputs

- Batch 8 and Batch 9 pass evidence plus one immutable `artifact_id` and target Snapshot.
- The affected service IDs, approved risk profiles, sanitized workload model and scenario scope.
- Named external authority, tool/config versions and append-only evidence workspace.

## Workflow

1. Verify admission, artifact binding, non-production isolation and the service-specific risk controls.
2. Validate restart, in-flight work, durable state and crash consistency.
3. Preserve raw evidence references, uncertainty, tool failures, abort reasons and open risks; never substitute Agent opinion for execution.
4. Return explicit `PASSED`, `FAILED`, `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE` or `NOT_APPLICABLE` status for every required check.

## Fail closed

- Block on data corruption, duplicate irreversible side effect or unreconciled in-flight work.
- Never access production resources, retain secrets, approve waivers, weaken thresholds or execute production deployment/cutover.
- A tool failure or missing, stale, duplicate or mismatched result remains blocked and is not silently retried into a pass.

## Output

Produce crash-point matrix, state reconciliation and recovery-time evidence. Bind every object to the immutable artifact and authority evidence. The strongest possible Batch 10 claim is eligibility for progressive delivery; always keep `production_ready=false` and `eligible_for_cutover=false`.

