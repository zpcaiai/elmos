---
name: "elmos-semantic-conflict-detector"
description: "Detect conflicts between independently valid patches that violate shared semantics, invariants or behavioral scenarios."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/49-semantic-conflict-detector/SKILL.md"
  source_sha256: "sha256:c26ede383ee98bce755132eee5c8acd3b7eb8622700ce1b0e4595a99182cce23"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "semantic_conflict_detector"
  canonical_owner: "canonical.elmos.verification-fabric"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/49-semantic-conflict-detector/SKILL.md` (`sha256:c26ede383ee98bce755132eee5c8acd3b7eb8622700ce1b0e4595a99182cce23`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Semantic Conflict Detector

Detect integration conflicts beyond textual merge conflicts.

## Inputs
- candidate patches
- task contracts
- scenario graph
- invariant ledger
- repository graph deltas

## Outputs
- `semantic conflict report`
- `affected scenarios`
- `resolution task requests`

## Procedure
1. Compare changes to shared symbols, schemas, config, data entities and side effects.
2. Detect incompatible assumptions even when git merges cleanly.
3. Re-evaluate shared invariants and edge contracts across combined patches.
4. Run targeted scenario probes on the merged state.
5. Generate a resolution task when conflicts cannot be solved mechanically.

## Acceptance criteria
- clean textual merge is never treated as sufficient integration evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
