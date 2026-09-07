---
name: elmos-repository-certifier
version: 1.0.0
description: Independently verify that all atomic changes compose into the original end-to-end requirement.
---

# Repository-Level Certifier

Independently verify that all atomic changes compose into the original end-to-end requirement.

## Trigger conditions
- all implementation waves integrated

## Inputs
- `normalized requirement`
- `integration branch`
- `all evidence`

## Outputs
- `certification report`
- `go/no-go`

## Procedure
1. Run clean build and full applicable regression.
2. Execute original acceptance scenarios end to end.
3. Validate requirement-to-task-to-evidence traceability.
4. Check no unowned/unexplained diff remains.
5. Use L3 model for semantic certification when model judgment is needed.

## Guardrails
- Leaf-task success cannot substitute for end-to-end acceptance.

## Acceptance criteria
- all final gates pass or explicit blocking findings recorded

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
