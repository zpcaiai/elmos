---
name: elmos-fde-execute-refactor
description: Plan and execute proof-guided atomic repository refactoring with isolated writes, ChangeSets, checkpoints, verification, and rollback.
---

# Purpose

Plan and execute proof-guided atomic repository refactoring with isolated writes, ChangeSets, checkpoints, verification, and rollback.

## Use this Skill when

- execute refactor
- apply transformation
- modernize repository
- repository-wide rewrite

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/docs/07_TRANSFORMATION_ENGINE.md`
- `${PACKAGE_ROOT}/skills/atomic/05-planning-transformation`
- `${PACKAGE_ROOT}/policies/approval-gates.yaml`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Require approved invariants, target architecture, Transformation DAG, and exact RevisionSet.
2. Prefer deterministic compiler/LST/AST/SIR transformations and isolate each write scope.
3. Intercept tool results and compare actual versus approved deltas before commit.
4. Run step-local and independent verification; stop on unknowns, scope drift, or failed proof obligations.
5. Commit atomically with provenance or roll back and update effects and evidence ledgers.

## Global constraints

- Preserve the existing Elmos K1-K8, Domain Pack, Goal, AI-SIR, runtime-authority and completion-authority ownership boundaries.
- All package component Skills are non-routable. Resolve `routeOwnerRef` against the target repository; do not invent a second route owner.
- Bind conclusions and changes to exact tenant, engagement, RevisionSet, environment, Skill, Adapter, tool and policy versions.
- Treat `UNKNOWN`, `UNSUPPORTED`, stale evidence, unresolved critical side effects and missing approvals as blockers when material.
- Use the least privileged tool capability. Production writes are prohibited by this capability package.
- Keep machine wall-clock, queue time, model/compute/storage/network/license cost and human review separate.
- A producer cannot self-approve. The maximum standalone package claim is E3 readiness.

## Before editing

1. Read the nearest applicable `AGENTS.md` files and `PLANS.md`.
2. Inspect `catalog/implementation-batches.yaml` and the exact task/Skill contracts.
3. Confirm the Git state, target write scope, tests and rollback path.
4. Record unresolved ambiguity as a decision or unknown; do not silently choose a semantic behavior.

## Required completion response

Report changed files, commands/tests executed, exact failures or warnings, evidence created, residual unknowns, rollback path and the next independent gate. Never state production readiness from specification generation alone.
