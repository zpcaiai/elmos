---
name: elmos-fde-create-adapter
description: Implement or update a replaceable Elmos Adapter with typed capabilities, trust boundaries, conformance tests, failure semantics, and no completion authority.
---

# Purpose

Implement or update a replaceable Elmos Adapter with typed capabilities, trust boundaries, conformance tests, failure semantics, and no completion authority.

## Use this Skill when

- create adapter
- integrate tool
- add MCP connector
- add analyzer provider

## Required reading

Read only the files needed for the active task. Do not bulk-load the whole package.

- `${PACKAGE_ROOT}/adapters`
- `${PACKAGE_ROOT}/docs/11_MCP_CONNECTOR_AND_ADAPTER_MODEL.md`
- `${PACKAGE_ROOT}/contracts/schemas/adapter-descriptor.schema.json`


Resolve `PACKAGE_ROOT` first: use the current directory when it contains `catalog/package.yaml`; otherwise locate exactly one `.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml`. Fail closed if none or more than one is found.

## Workflow

1. Select an existing abstract port and prove a new Adapter is needed.
2. Define supported operations, data classes, side effects, authentication, rate limits, version negotiation, and failure semantics.
3. Enforce capability leases, verified security context, environment ownership, result typing, and fencing.
4. Add positive, negative, timeout, retry, idempotency, stale-version, and tenant-isolation conformance tests.
5. Register the Adapter without granting semantic truth or completion authority.

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
