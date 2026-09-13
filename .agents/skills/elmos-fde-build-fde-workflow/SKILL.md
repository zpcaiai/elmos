---
name: elmos-fde-build-fde-workflow
description: Implement customer discovery, scope, SOW, status, adoption, procurement, and handoff workflows as evidence-backed Elmos product features.
---

# Purpose

Implement customer discovery, scope, SOW, status, adoption, procurement, and handoff workflows as evidence-backed Elmos product features.

## Use this Skill when

- build FDE workflow
- customer delivery hub
- SOW automation
- adoption workflow

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/docs/01_FDE_JOB_TO_PRODUCT_CAPABILITY_MAP.md`
- `${PACKAGE_ROOT}/skills/atomic/01-fde-engagement`
- `${PACKAGE_ROOT}/docs/10_UI_UX_AND_WORKSPACES.md`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Choose one persona and critical FDE journey rather than building a generic CRM.
2. Model observed facts, stakeholder claims, decisions, unknowns, scope, acceptance, actions, and evidence as typed entities.
3. Implement collaborative review, approvals, role permissions, exports, and connector boundaries.
4. Derive status and reports from ledgers and acceptance state, not generated prose alone.
5. Instrument adoption and value without collecting data outside tenant consent.

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
