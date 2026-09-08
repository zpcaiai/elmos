---
name: "elmos-implicit-requirement-miner"
description: "Recover implicit repository requirements from executable and structural evidence before implementation planning."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/37-implicit-requirement-miner/SKILL.md"
  source_sha256: "sha256:76e79ffa7e84b17580274c97e4e86c826cca02b7e3ba4fdc70cdd6864a504ab7"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "implicit_requirement_miner"
  canonical_owner: "canonical.elmos.requirement-baseline"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/37-implicit-requirement-miner/SKILL.md` (`sha256:76e79ffa7e84b17580274c97e4e86c826cca02b7e3ba4fdc70cdd6864a504ab7`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Implicit Requirement Miner

Recover requirements that are not stated in the user prompt but are encoded in the repository.

## Trigger conditions
- normalized requirement exists
- repository intake is available

## Inputs
- `requirement spec`
- `repository intelligence graph`
- `tests/build/config/public interfaces`

## Outputs
- `explicit requirement set`
- `inferred requirement set`
- `evidence links`
- `ambiguity ledger`
- `exploration task requests`

## Procedure
1. Trace every requested behavior to existing tests, public APIs, schemas, examples and sibling implementations.
2. Infer compatibility, error, security, persistence, observability and lifecycle expectations only when repository evidence exists.
3. Tag each inference with source evidence, confidence and consequences if wrong.
4. Detect contradictions between prompt, code, tests and documentation.
5. Convert unresolved high-impact ambiguity into an exploration task instead of silently guessing.
6. Feed confirmed/inferred requirements into scenario graph generation.

## Guardrails
- Never invent hidden requirements without repository evidence.
- Treat tests as behavioral evidence, not automatically as the complete product specification.
- High-risk ambiguity blocks irreversible implementation until explored or explicitly waived.

## Acceptance criteria
- every inferred requirement has evidence and confidence
- contradictions are explicit
- no critical ambiguity is silently embedded in downstream tasks

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
