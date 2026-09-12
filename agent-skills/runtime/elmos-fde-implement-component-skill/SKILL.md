---
name: elmos-fde-implement-component-skill
description: Implement one atomic Elmos FDE component Skill and all required contracts, ports, workflows, tests, telemetry, and evidence hooks.
---

# Purpose

Implement one atomic Elmos FDE component Skill and all required contracts, ports, workflows, tests, telemetry, and evidence hooks.

## Use this Skill when

- implement atomic skill
- build one capability
- complete skill contract

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/skills/atomic`
- `${PACKAGE_ROOT}/contracts/schemas`
- `${PACKAGE_ROOT}/docs/03_DOMAIN_MODEL_AND_LEDGERS.md`
- `${PACKAGE_ROOT}/templates`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Select exactly one atomic Skill and read all five contract files.
2. Map its ports to existing Elmos owners and adapters; do not add duplicate stores or authorities.
3. Write failing contract, policy, authority, idempotency, resume, isolation, and acceptance tests first.
4. Implement the minimum native vertical behavior, persistence, APIs, events, and telemetry.
5. Run independent review, package traceability, and evidence checks before marking specification tasks complete.

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
