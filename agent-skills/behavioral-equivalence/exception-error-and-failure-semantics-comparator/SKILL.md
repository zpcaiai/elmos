---
name: exception-error-and-failure-semantics-comparator
description: "Compare Batch 9 exceptions, result errors, HTTP failures, process exits, async faults, timeout and cancellation. Use for normal, boundary and injected-failure paths."
---

# Exception Error and Failure Semantics Comparator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Map runtime-specific exceptions to reviewed logical error types.
2. Compare failure channel/time, code, structured fields, cause, HTTP mapping, retryability, rollback and visibility.
3. Separate dynamic text from contract messages without swallowing meaning.

## Hard rules

- Never equate success with failure, timeout with cancellation, or business with system error.
- Do not hide lost causes or newly exposed internals.
- Compare async fault versus synchronous throw semantics.

## Output

Emit logical/runtime error diffs and security exposure findings.

