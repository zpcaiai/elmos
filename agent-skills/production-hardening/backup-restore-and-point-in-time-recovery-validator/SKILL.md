---
name: backup-restore-and-point-in-time-recovery-validator
description: "Use when Batch 10 must validate backup integrity, restore isolation and required point-in-time recovery."
---

# Backup Restore And Point In Time Recovery Validator

Read `../references/batch-10-production-hardening.md` completely before acting. Use `modules/production-hardening` for gate semantics and validate machine artifacts against `contracts/production-hardening-schema`.

## Required inputs

- Batch 8 and Batch 9 pass evidence plus one immutable `artifact_id` and target Snapshot.
- The affected service IDs, approved risk profiles, sanitized workload model and scenario scope.
- Named external authority, tool/config versions and append-only evidence workspace.

## Workflow

1. Verify admission, artifact binding, non-production isolation and the service-specific risk controls.
2. Validate backup integrity, restore isolation and required point-in-time recovery.
3. Preserve raw evidence references, uncertainty, tool failures, abort reasons and open risks; never substitute Agent opinion for execution.
4. Return explicit `PASSED`, `FAILED`, `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE` or `NOT_APPLICABLE` status for every required check.

## Fail closed

- Block on untested backup, failed restore, production overwrite or unmet recovery point.
- Never access production resources, retain secrets, approve waivers, weaken thresholds or execute production deployment/cutover.
- A tool failure or missing, stale, duplicate or mismatched result remains blocked and is not silently retried into a pass.

## Output

Produce restore and PITR evidence bound to backup, schema and artifact versions. Bind every object to the immutable artifact and authority evidence. The strongest possible Batch 10 claim is eligibility for progressive delivery; always keep `production_ready=false` and `eligible_for_cutover=false`.

