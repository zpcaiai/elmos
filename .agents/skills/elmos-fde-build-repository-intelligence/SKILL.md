---
name: elmos-fde-build-repository-intelligence
description: Implement repository intake, runtime reproduction, support profiling, semantic graph, lineage, and evidence fusion capabilities.
---

# Purpose

Implement repository intake, runtime reproduction, support profiling, semantic graph, lineage, and evidence fusion capabilities.

## Use this Skill when

- repository intelligence
- semantic graph
- runtime lab
- source intake

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/docs/06_REPOSITORY_SEMANTIC_SYSTEM_GRAPH.md`
- `${PACKAGE_ROOT}/skills/atomic/02-repository-intake-runtime`
- `${PACKAGE_ROOT}/skills/atomic/03-semantic-intelligence`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Implement RevisionSet and custody before analysis.
2. Implement inventory and support-depth reporting before claiming semantic coverage.
3. Add hermetic runtime reproduction and service virtualization with environment-owned authority.
4. Build incremental typed graph layers and fuse static/runtime evidence with provenance.
5. Validate with polyglot fixtures, dynamic ambiguity, stale-evidence, and million-line scale tests.

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
