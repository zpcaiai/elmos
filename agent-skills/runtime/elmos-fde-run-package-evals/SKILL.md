---
name: elmos-fde-run-package-evals
description: Validate this skills package, Codex trigger behavior, schemas, dependency DAG, examples, installers, reference kernel, and negative controls.
---

# Purpose

Validate this skills package, Codex trigger behavior, schemas, dependency DAG, examples, installers, reference kernel, and negative controls.

## Use this Skill when

- validate package
- run skill evals
- test Codex skills
- release package

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/evals`
- `${PACKAGE_ROOT}/scripts`
- `${PACKAGE_ROOT}/tests`
- `${PACKAGE_ROOT}/docs/16_CODEX_USAGE_GUIDE.md`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Run validate.sh and inspect all warnings rather than reporting PASS from exit code alone.
2. Run unit tests, schema examples, dependency checks, local links, secret scan, and install/uninstall smoke tests.
3. Run Codex skill trigger evals explicitly, contextually, negatively, and on adjacent intents using structured JSONL traces.
4. Build deterministic ZIP and TAR.GZ archives twice and compare file sets and hashes.
5. Write BUILD_REPORT.md with executed and unexecuted checks and the exact completion boundary.

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
