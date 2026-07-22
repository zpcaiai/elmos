---
name: b33-helm-chart-migration
description: "Migrate and certify Helm charts values schemas templates hooks dependencies releases upgrades rollbacks tests ownership and rendered Kubernetes contracts without hiding behavior in templates."
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

## Skill 1229: Helm chart migration

## Use this skill when

- A Helm chart must be modernized, split, consolidated, moved between clusters, or converted from/to another packaging strategy.
- Chart values or templates lack schemas, deterministic rendering, upgrade tests, or ownership.
- Hooks and release lifecycle need explicit migration.

## Domain-specific risks and invariants

- Helm behavior includes merge semantics, values precedence, templates, lookup, hooks, CRDs, dependencies, release history, ownership labels, and upgrade behavior.
- Rendered YAML alone cannot prove upgrade/rollback correctness.
- Hooks can create untracked side effects and orphan resources.

## Workflow

1. Inventory chart API version, dependencies, values layers, schemas, templates, functions, lookups, hooks, CRDs, tests, release history, and live ownership.
2. Emit chart intent into IaC IR and runtime contracts; identify provider/cluster-specific values.
3. Create target chart with explicit values schema, deterministic templates, pinned dependencies, and documented ownership.
4. Preserve or redesign hooks with idempotency, timeout, rollback, and cleanup.
5. Run lint, render, schema, policy, and server-side validation for representative value sets.
6. Install, upgrade from supported source releases, rollback, run tests, and uninstall in an isolated cluster.
7. Verify all namespaced, cluster-scoped, and cloud-integrated resources are removed or retained by explicit policy.

## Required repository outputs

- Target chart, values schema, migration guide, and compatibility matrix
- Rendered-manifest snapshots for development and holdout values
- Install/upgrade/rollback/uninstall evidence
- Hook and ownership inventory

## Verification

- Run exact Helm and Kubernetes versions.
- Test fresh install, N-1 supported upgrade, failure rollback, and uninstall.
- Validate values merge, required values, secret references, policies, and live ownership.
- Run holdout values not used while authoring templates.

## Stop and escalate when

- Hooks are non-idempotent or destructive without safe compensation.
- CRD ownership or upgrade strategy is unknown.
- Chart depends on live cluster lookup that cannot be reproduced.
- Uninstall leaves unapproved resources or data.

## Definition of done

- Chart renders deterministically, validates, installs, upgrades, rolls back, tests, and uninstalls on certified target profiles with explicit hooks, CRDs, values, ownership, and evidence.
