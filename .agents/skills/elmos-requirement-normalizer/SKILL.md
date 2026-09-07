---
name: "elmos-requirement-normalizer"
description: "Normalize explicit requirements and separate repository-discoverable unknowns from product ambiguities before planning."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/01-requirement-normalizer/SKILL.md"
  source_sha256: "sha256:0fa24cc134702a355679ddcb62581ae6b8c9e66f407dd8410a7804c9dcb3d89e"
  namespace: "repository-task-router-v2"
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

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/01-requirement-normalizer/SKILL.md` (`sha256:0fa24cc134702a355679ddcb62581ae6b8c9e66f407dd8410a7804c9dcb3d89e`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Requirement Normalizer v2

Convert the raw request into an evidence-oriented specification without prematurely choosing implementation files.

## Inputs
- `raw requirement`
- `repo metadata`

## Outputs
- `explicit requirement spec`
- `non-goals`
- `constraints`
- `observable acceptance criteria`
- `unknown/ambiguity ledger`

## Procedure
1. Extract business objective, user-visible outcome and system-visible side effects.
2. Separate functional, non-functional, compatibility and operational constraints.
3. Identify explicit non-goals and irreversible decisions.
4. Turn each must-have into observable acceptance criteria, not implementation prescriptions.
5. Split unknowns into repository-discoverable, product-decision and external-dependency classes.
6. Route repository-discoverable unknowns to `elmos-implicit-requirement-miner`; never ask the user for facts the repository can answer.
7. Assign consequence-of-error and confidence to each unresolved ambiguity.

## Guardrails
- Do not infer hidden requirements here; that requires repository evidence.
- Do not decompose by files until behavioral scenarios and repository graph exist.

## Acceptance criteria
- every must-have maps to observable evidence
- unknowns are classified and high-impact ambiguity is visible

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
