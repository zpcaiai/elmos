---
name: elmos-fde-package-navigator
description: Navigate this Elmos FDE package, select the right specifications, and explain boundaries before implementation.
---

# Purpose

Navigate this Elmos FDE package, select the right specifications, and explain boundaries before implementation.

## Use this Skill when

- understand package
- find relevant skill
- what should Codex implement
- package map

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/README.md`
- `${PACKAGE_ROOT}/AGENTS.md`
- `${PACKAGE_ROOT}/catalog/skill-catalog.yaml`
- `${PACKAGE_ROOT}/docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md`
- `${PACKAGE_ROOT}/docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Identify the user's intended business line, lifecycle phase, repository scope, risk, and desired evidence level.
2. Search the catalog and choose the smallest set of atomic Skills; do not activate every capability.
3. Load only the selected Skill contracts and directly relevant shared documents.
4. State canonical K1-K8 ownership, dependencies, blockers, and the E3 boundary.
5. Return a concise implementation or execution path with file references.

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
