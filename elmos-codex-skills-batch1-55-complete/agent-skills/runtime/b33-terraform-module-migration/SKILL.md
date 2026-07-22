---
name: b33-terraform-module-migration
description: "Migrate and certify Terraform modules providers state addresses imports moves lifecycle expressions backends locks plans applies upgrades drift and destroy with exact provider and CLI versions."
---

## Operating mode

Work directly in the repository. Inspect existing Batch 20-32 contracts, deployment files, cloud accounts or approved sandboxes, state backends, CI/CD configuration, security policies, runtime telemetry, tests, and evidence before editing. Implement the smallest production-shaped infrastructure or delivery vertical slice that satisfies this skill; do not stop at architecture notes when executable discovery, typed contracts, transformations, plans, sandbox applies, runtime checks, cleanup, and evidence can be added.

Read these shared contracts first:

- `../../../docs/batch33/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch33/QUALITY_GATES.md`
- `../../../docs/batch33/REPOSITORY_LAYOUT.md`
- `../../../docs/batch33/CLOUD_MATRIX.md`
- `../../../docs/batch33/VERSION_LIFECYCLE.md`
- `../../../docs/batch33/SECURITY_POLICY.md`
- `../../../docs/batch33/DRIFT_COST_AND_CLEANUP_POLICY.md`
- `../../../docs/batch33/PROVIDER_PROFILES.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch33/scaffold_cloud_pack.py ...`
- `python3 scripts/batch33/validate_cloud_pack.py ...`
- `python3 scripts/batch33/validate_runtime_contract.py ...`
- `python3 scripts/batch33/validate_iac_ir.py ...`
- `python3 scripts/batch33/run_cloud_gate.py ...`

## Global constraints

- Treat every pack as directional, exact, provider/version/region/account-model/tool/runtime specific, and independently certified. A reverse route, another region model, or another target provider is a separate tuple or pack.
- Capture static definitions and actual runtime facts: resources, identities, networks, DNS, data flows, CI/CD, images, state, managed services, quotas, policies, telemetry, cost, and drift. Do not infer production reality from templates alone.
- Transform through a typed Runtime Architecture Contract and provider-neutral IaC IR. Do not implement complex migrations as regex or raw text substitution.
- Run real source and target validation. Certification requires real plans and, where safe and applicable, apply/runtime evidence from approved ephemeral accounts, subscriptions, projects, clusters, emulators, or local integration environments.
- Preserve availability, scaling, rollout, health, identity, least privilege, network boundaries, DNS, encryption, data classification, residency, retention, backup, recovery, observability, audit, and cost constraints.
- Never broaden IAM, expose a private service publicly, disable policy checks, embed secrets, use floating image or action versions, or skip cleanup merely to obtain a successful plan or deployment.
- Keep development, negative, holdout, and representative workload corpora physically separate. Do not tune mappings, security exceptions, cost tolerances, or drift rules from holdout cases.
- Prefer deterministic transformations, certified modules, and explicit adapters. Model-generated IaC, pipelines, policies, or tests are candidates and must pass the same plan, apply, runtime, security, drift, cost, rollback, and destroy gates.
- Fix repeated failures in discovery, contracts, IaC IR, capability mapping, target profiles, transformations, or modules instead of patching many generated resources independently.
- Protect customer-owned infrastructure and state. Import, ownership, moved resources, replacement, coexistence, and destroy behavior must be explicit before apply.
- Use isolated state, credentials, accounts, namespaces, networks, and resource naming for tests. Record TTL, owner, budget, and cleanup evidence.
- Run the narrowest relevant checks first, then independent holdout and representative workloads, and finally the conservative Batch 33 gate before making release claims.

## Skill 1230: Terraform module and state migration

## Use this skill when

- Terraform modules, providers, state, workspaces, or backends must be modernized or used as a target.
- CloudFormation, Bicep, scripts, or manual resources need a Terraform target.
- Existing Terraform lacks state ownership, provider locking, upgrade, drift, or destroy evidence.

## Domain-specific risks and invariants

- Terraform behavior depends on provider schemas, graph construction, unknown values, state addresses, imports, moved blocks, lifecycle, backends, locks, and version constraints.
- A syntactically valid module can replace live resources unexpectedly.
- State manipulation is high risk and must be rehearsed.

## Workflow

1. Inventory exact Terraform/OpenTofu CLI, provider locks, modules, backends, workspaces, variables, outputs, state addresses, imports, lifecycle, provisioners, data sources, and CI execution.
2. Parse modules and state into IaC IR; map live resources and ownership.
3. Generate or refactor target modules with explicit versions, validation, sensitive values, outputs, lifecycle, import/move strategy, tags, identity, network, and policies.
4. Create isolated backend and plan fixtures; test import and moved-address scenarios.
5. Run fmt, validate, provider schema, plan, policy, apply, refresh-only/drift, upgrade, rollback/forward recovery, and destroy.
6. Compare live target resources and Runtime Architecture Contract.
7. Record state-backend encryption, locking, backup, recovery, and operator access.

## Required repository outputs

- Target modules, lock files, backend profile, import/move plan, and state ownership manifest
- Plan/apply/drift/destroy and provider-upgrade evidence
- Negative fixtures for replacement, unknown values, secret output, and state conflict
- Holdout module/workload cases

## Verification

- Use exact CLI and provider versions.
- Review plan JSON for create/update/replace/delete, unknown values, sensitive fields, IAM, network, data, and cost.
- Exercise backend locking and recovery.
- Apply and destroy in isolation; verify no orphaned resources/state.

## Stop and escalate when

- State ownership or live-resource identity is ambiguous.
- A required change would destroy or replace protected data without approved migration.
- Provider behavior cannot be locked or validated.
- Provisioners or external scripts have unknown side effects.

## Definition of done

- Modules and state migrate without unapproved replacement, secret leakage, drift, or orphaned resources; plans, applies, imports/moves, upgrades, recovery, and destroy are evidenced.
