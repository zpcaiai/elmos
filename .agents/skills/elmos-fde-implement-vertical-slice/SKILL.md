---
name: elmos-fde-implement-vertical-slice
description: Implement an end-to-end FDE or repository-refactoring vertical slice across UI, API, workflow, workers, ledgers, policies, and tests.
---

# Purpose

Implement an end-to-end FDE or repository-refactoring vertical slice across UI, API, workflow, workers, ledgers, policies, and tests.

## Use this Skill when

- implement vertical slice
- build end to end
- first commercial workflow

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/docs/02_REFERENCE_ARCHITECTURE.md`
- `${PACKAGE_ROOT}/docs/10_UI_UX_AND_WORKSPACES.md`
- `${PACKAGE_ROOT}/docs/14_GOLDEN_ROUTES.md`
- `${PACKAGE_ROOT}/catalog/implementation-backlog.json`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Choose one approved Golden Route and one critical user journey.
2. Implement the thinnest complete path from user intent to evidence-backed output.
3. Reuse canonical K1-K8 services and add adapters only at replaceable boundaries.
4. Include tenant isolation, policy, authority, checkpoints, cancellation, cost, progress, and rollback from the first slice.
5. Demonstrate the route on fixtures and produce an E0-E3 evidence packet without production claims.

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
