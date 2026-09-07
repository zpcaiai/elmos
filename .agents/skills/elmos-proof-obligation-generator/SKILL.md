---
name: "elmos-proof-obligation-generator"
description: "Translate requirements and invariants into executable or inspectable proof obligations attached to tasks and edges."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/46-proof-obligation-generator/SKILL.md"
  source_sha256: "sha256:76cb7047897792976c3753767d20cca298c0b6e1fa10bc97624effb31a307081"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "proof_obligation_generator"
  canonical_owner: "canonical.elmos.verification-fabric"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/46-proof-obligation-generator/SKILL.md` (`sha256:76cb7047897792976c3753767d20cca298c0b6e1fa10bc97624effb31a307081`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Proof Obligation Generator

Define what must be proven before a task or boundary can be accepted.

## Inputs
- scenario graph
- invariant ledger
- task plan

## Outputs
- `proof obligations`
- `preferred verifier type`
- `evidence requirements`

## Procedure
1. Generate obligations for functional behavior, negative behavior, compatibility, security, migration, concurrency and side effects.
2. Prefer deterministic evidence: compiler, tests, static analyzers, executable probes and structured diffs.
3. Assign obligations to the smallest task or integration gate capable of proving them.
4. Mark obligations that require independent or repository-level verification.
5. Reject leaf completion when mandatory obligations remain open.

## Acceptance criteria
- every acceptance criterion and critical invariant maps to proof evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
