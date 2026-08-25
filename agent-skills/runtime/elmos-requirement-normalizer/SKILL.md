---
name: "elmos-requirement-normalizer"
description: "Convert ambiguous product/engineering requests into explicit scope, non-goals, constraints, acceptance scenarios and unknowns without prematurely coding."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/01-requirement-normalizer/SKILL.md"
  source_sha256: "sha256:69f5f54e8fedf77585ef8d8cb0e584db415be1a23dbc67574dbcf868c85a0305"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "requirement_normalizer"
  canonical_owner: "canonical.elmos.requirement-baseline"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/01-requirement-normalizer/SKILL.md` (`sha256:69f5f54e8fedf77585ef8d8cb0e584db415be1a23dbc67574dbcf868c85a0305`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Requirement Normalizer

Convert ambiguous product/engineering requests into explicit scope, non-goals, constraints, acceptance scenarios and unknowns without prematurely coding.

## Trigger conditions
- new feature request
- multi-paragraph requirement
- ambiguous repository task

## Inputs
- `raw requirement`
- `repo metadata`

## Outputs
- `normalized requirement spec`
- `acceptance scenarios`
- `assumption log`

## Procedure
1. Extract business objective and user-visible outcomes.
2. Separate functional/non-functional requirements.
3. List explicit non-goals and invariants.
4. Turn each must-have into observable acceptance scenarios.
5. Record assumptions that can be validated from the repository.

## Guardrails
- Do not invent external requirements.
- Resolve repository-discoverable questions by inspection rather than asking.

## Acceptance criteria
- each must-have maps to >=1 acceptance scenario
- unknowns are classified

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
