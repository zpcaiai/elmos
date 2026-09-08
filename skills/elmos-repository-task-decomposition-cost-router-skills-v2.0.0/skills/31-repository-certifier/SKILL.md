---
name: elmos-repository-certifier
version: 2.0.0
description: Independently prove that the final integrated repository satisfies original explicit/implicit requirements and preserves required invariants.
---

# Repository-Level Certifier v2

Certify the complete repository change against behavior, architecture and evidence.

## Inputs
- `explicit + evidence-backed implicit requirements`
- `scenario graph`
- `invariant ledger`
- `integration branch`
- `baselines`
- `all task/edge proof evidence`

## Outputs
- `certification report`
- `go/no-go`
- `requirement-to-scenario-to-task-to-proof traceability matrix`

## Procedure
1. Run clean build and full applicable regression from a reproducible environment.
2. Execute original behavioral scenarios, including negative/compatibility/rollback cases.
3. Verify all critical invariants and proof obligations are closed.
4. Compare against baselines/golden outputs and inspect unexplained diff surfaces.
5. Validate no scenario or inferred requirement became orphaned through replanning.
6. Use an independent high-tier model only where deterministic evidence cannot resolve semantic correctness.
7. Record unresolved uncertainty and certification limitations explicitly.

## Guardrails
- Leaf-task success or model confidence cannot substitute for repository-level proof.

## Acceptance criteria
- all mandatory scenarios/invariants/proofs pass or produce blocking findings

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
