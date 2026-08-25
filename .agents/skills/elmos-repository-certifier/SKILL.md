---
name: "elmos-repository-certifier"
description: "Independently verify that all atomic changes compose into the original end-to-end requirement."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/31-repository-certifier/SKILL.md"
  source_sha256: "sha256:ff49131d3072a17c2e33b0226b7fbf45e8677a8ad4e1c58e3d0981215cde4bcc"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "repository_certifier"
  canonical_owner: "canonical.elmos.local-verification-gate"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/31-repository-certifier/SKILL.md` (`sha256:ff49131d3072a17c2e33b0226b7fbf45e8677a8ad4e1c58e3d0981215cde4bcc`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
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
