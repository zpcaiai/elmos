---
name: b33-cloud-native-iac-migration
description: "Migrate and certify CloudFormation Bicep ARM templates deployment stacks and other cloud-native IaC into exact targets while preserving conditions dependencies lifecycle policies identities and deployment state."
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

## Skill 1231: CloudFormation, Bicep, and cloud-native IaC migration

## Use this skill when

- Cloud-native templates need version upgrade, modularization, cross-tool conversion, or cross-provider migration.
- CloudFormation stacks, ARM/Bicep deployments, deployment scripts, or nested templates need certified handling.
- A target Terraform or alternate native template must preserve deployment semantics.

## Domain-specific risks and invariants

- Native IaC semantics include conditions, intrinsic functions, nested stacks/modules, deployment modes, stack policies, rollback, change sets, drift, and provider-managed state.
- Tool conversion can alter replacement and ownership behavior.
- Custom resources and deployment scripts may execute arbitrary side effects.

## Workflow

1. Inventory exact template/version, stacks/deployments, nested modules, parameters, outputs, conditions, intrinsic functions, policies, custom resources, scripts, state, and live drift.
2. Parse into typed IaC IR with provider extensions and source maps.
3. Map to exact target tool/profile with explicit replacement, import, coexistence, and ownership strategies.
4. Implement custom-resource or deployment-script adapters only with bounded interfaces, identity, idempotency, timeout, rollback, and evidence.
5. Run source change set/what-if and target plan; compare resource graph and lifecycle.
6. Apply in an isolated environment, test updates and rollback, detect drift, and clean up.
7. Create migration guide for state/stack ownership and production cutover.

## Required repository outputs

- Typed source adapter and target emitter
- Resource graph/lifecycle comparison
- Custom resource/script inventory and adapters
- Change-set/what-if, plan, apply, rollback, drift, and cleanup evidence

## Verification

- Run exact native tooling and target tooling.
- Compare create/update/replace/delete and policy effects.
- Exercise nested modules, conditions, failure rollback, drift, and one custom-resource path if in scope.
- Verify no unmanaged or orphaned resources.

## Stop and escalate when

- Custom resources or deployment scripts have unknown/unbounded side effects.
- Stack/deployment ownership cannot be reconciled with target state.
- Protected resources require unapproved replacement.
- Rollback behavior cannot be exercised safely.

## Definition of done

- The certified scope preserves resource, condition, dependency, lifecycle, policy, identity, state, rollback, and cleanup semantics with real source/target evidence.
