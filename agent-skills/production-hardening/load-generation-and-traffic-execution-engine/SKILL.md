---
name: load-generation-and-traffic-execution-engine
description: "Use when Batch 10 must execute an approved load plan through an external isolated load authority."
---

# Load Generation And Traffic Execution Engine

Read `../references/batch-10-production-hardening.md` completely before acting. Use `modules/production-hardening` for gate semantics and validate machine artifacts against `contracts/production-hardening-schema`.

## Required inputs

- Batch 8 and Batch 9 pass evidence plus one immutable `artifact_id` and target Snapshot.
- The affected service IDs, approved risk profiles, sanitized workload model and scenario scope.
- Named external authority, tool/config versions and append-only evidence workspace.

## Workflow

1. Verify admission, artifact binding, non-production isolation and the service-specific risk controls.
2. Execute an approved load plan through an external isolated load authority.
3. Preserve raw evidence references, uncertainty, tool failures, abort reasons and open risks; never substitute Agent opinion for execution.
4. Return explicit `PASSED`, `FAILED`, `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE` or `NOT_APPLICABLE` status for every required check.

## Fail closed

- Block on unapproved execution, production traffic, generator saturation or missing raw results.
- Never access production resources, retain secrets, approve waivers, weaken thresholds or execute production deployment/cutover.
- A tool failure or missing, stale, duplicate or mismatched result remains blocked and is not silently retried into a pass.

## Output

Produce execution records linked to generator, environment, artifact and scenario versions. Bind every object to the immutable artifact and authority evidence. The strongest possible Batch 10 claim is eligibility for progressive delivery; always keep `production_ready=false` and `eligible_for_cutover=false`.

