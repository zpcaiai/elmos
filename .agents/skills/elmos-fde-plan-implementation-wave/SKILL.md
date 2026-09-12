---
name: elmos-fde-plan-implementation-wave
description: Plan a bounded Elmos implementation wave from package backlog, dependencies, risks, contracts, and acceptance gates.
---

# Purpose

Plan a bounded Elmos implementation wave from package backlog, dependencies, risks, contracts, and acceptance gates.

## Use this Skill when

- plan implementation batch
- create execution plan
- choose next P0 work
- implementation wave

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/catalog/implementation-backlog.json`
- `${PACKAGE_ROOT}/docs/15_IMPLEMENTATION_ROADMAP.md`
- `${PACKAGE_ROOT}/PLANS.md`
- `${PACKAGE_ROOT}/catalog/dependency-graph.json`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Inspect the target repository and its existing canonical contracts before choosing work.
2. Select one vertical slice or dependency-closed batch; avoid simultaneous broad rewrites.
3. Resolve exact affected atomic Skills, schemas, adapters, migrations, APIs, events, UI, and tests.
4. Write an ExecPlan using PLANS.md with red-green-refactor, evidence, rollback, and independent review gates.
5. Separate machine wall-clock, queue, cost, and human approvals.

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
