---
name: elmos-fde-verify-change
description: Independently verify an Elmos or customer code change using contracts, differential tests, mutation, risk-based non-functional checks, and evidence gates.
---

# Purpose

Independently verify an Elmos or customer code change using contracts, differential tests, mutation, risk-based non-functional checks, and evidence gates.

## Use this Skill when

- verify change
- review refactor
- behavior equivalence
- E3 readiness

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/docs/08_VERIFICATION_AND_E0_E3.md`
- `${PACKAGE_ROOT}/skills/atomic/06-verification-release-operations`
- `${PACKAGE_ROOT}/templates/evidence-bundle.md`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Do not rely on producer summaries; reconstruct exact inputs, changes, environment, and obligations.
2. Map every changed behavior and risk to independent checks.
3. Run compile, static, tests, differential, mutation, performance, security, migration, and recovery checks as applicable.
4. Retain counterexamples, unknowns, unsupported paths, and stale-evidence blockers.
5. Return evidence and a recommendation to K8; never self-issue E4/E5/P05 or production certification.

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
