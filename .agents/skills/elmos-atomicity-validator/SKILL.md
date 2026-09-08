---
name: "elmos-atomicity-validator"
description: "Validate executable leaves for semantic cohesion, safe boundaries, verification locality and handoff completeness; recommend split or merge."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/06-atomicity-validator/SKILL.md"
  source_sha256: "sha256:b7b4bf463214da951e7287c586b4799d53a3fb4fc427eac1d5c566e839640e64"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "atomicity_validator"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/06-atomicity-validator/SKILL.md` (`sha256:b7b4bf463214da951e7287c586b4799d53a3fb4fc427eac1d5c566e839640e64`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Atomicity Validator v2

Validate that a leaf is the smallest *safe and economical* independently executable unit, not simply a small patch.

## Inputs
- `candidate tasks`
- `granularity scores`
- `invariant ledger`
- `handoff contracts`

## Outputs
- `validated leaves`
- `split/merge recommendations`
- `atomicity exceptions`

## Procedure
1. Check one semantic objective and bounded write ownership.
2. Check local or explicitly delegated proof obligations.
3. Reject leaves that depend on hidden shared state or undocumented assumptions.
4. Split over-large leaves only at approved semantic seams.
5. Merge over-split leaves when handoff/coupling cost exceeds independent execution benefit.
6. Require owned/read/forbidden paths, scenario links, invariant links and incoming/outgoing contract IDs.
7. Allow larger units for indivisible transactions, migrations or concurrency protocols with an explicit exception reason.

## Guardrails
- `small` is neither necessary nor sufficient for atomicity.

## Acceptance criteria
- no executable leaf has unresolved hidden dependencies or critical invariant gaps

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
