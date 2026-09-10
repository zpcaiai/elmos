---
name: elmos-fde-audit-existing-repository
description: Assess an existing Elmos or customer repository against this package and produce an evidence-backed gap, risk, and implementation report.
---

# Purpose

Assess an existing Elmos or customer repository against this package and produce an evidence-backed gap, risk, and implementation report.

## Use this Skill when

- audit existing repo
- gap assessment
- evaluate current implementation
- repository health

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/docs/04_REQUIREMENTS_AND_SCENARIOS.md`
- `${PACKAGE_ROOT}/catalog/requirements.json`
- `${PACKAGE_ROOT}/catalog/issue-ontology.json`
- `${PACKAGE_ROOT}/templates/repository-assessment-report.md`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Freeze the exact repository RevisionSet and inspect existing AGENTS, architecture, schemas, tests, workflows, and deployment files.
2. Delegate read-heavy audits by issue domain; keep the main thread on scope and synthesis.
3. Validate findings with deterministic evidence and record unknown or unsupported areas.
4. Map gaps to atomic Skills, implementation batches, acceptance gates, risk, and machine wall-clock ranges.
5. Produce management, technical, executable, and evidence deliverables; do not edit unless explicitly asked.

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
