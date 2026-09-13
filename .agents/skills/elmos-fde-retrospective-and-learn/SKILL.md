---
name: elmos-fde-retrospective-and-learn
description: Run a materiality-based retrospective and place each improvement in the correct Elmos or Codex ownership layer.
---

# Purpose

Run a materiality-based retrospective and place each improvement in the correct Elmos or Codex ownership layer.

## Use this Skill when

- retrospective
- postmortem improvement
- update skill
- learn from delivery

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md`
- `${PACKAGE_ROOT}/skills/atomic/06-verification-release-operations/reusable-recipe-skill-learning`
- `${PACKAGE_ROOT}/templates/retrospective.md`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Include only events that materially affected scope, correctness, evidence, security, reliability, approval, reproducibility, or repeated effort.
2. Classify each lesson into AGENTS, project harness, existing Skill instruction/reference/script, regression test, Adapter, policy, new Skill, or no change.
3. Prefer tightening existing ownership over creating a new capability.
4. Sanitize tenant evidence and verify consent before reusable learning.
5. Add evals and invalidation triggers for every durable improvement.

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
