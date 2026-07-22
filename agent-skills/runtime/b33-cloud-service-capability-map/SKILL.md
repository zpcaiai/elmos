---
name: b33-cloud-service-capability-map
description: "Map source cloud services and operational capabilities to target services modules adapters coexistence or blocked strategies with explicit identity network data availability recovery cost and lifecycle evidence."
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

## Skill 1226: Cloud service capability and provider mapping

## Use this skill when

- A source managed service needs a target equivalent or replacement strategy.
- Cross-provider modernization requires comparison beyond product names.
- A service mapping lacks availability, consistency, security, operational, or cost evidence.

## Domain-specific risks and invariants

- Services with similar marketing labels can differ in consistency, failover, quotas, identity, networking, backup, encryption, observability, and billing.
- A direct service replacement can alter data contracts and operational responsibilities.
- Some source services should be retained, wrapped, or migrated via coexistence rather than replaced.

## Workflow

1. Extract source service tier, version, region, topology, availability, consistency, backup, encryption, IAM, network, quotas, observability, data size, workload, and cost facts.
2. Define provider-neutral capability requirements and non-negotiable P0 contracts.
3. Evaluate target candidates as direct map, replatform, adapter, self-managed, sidecar, retain, coexist, or blocked.
4. Implement the selected mapping in target profile and IaC transformations, including migration and rollback dependencies.
5. Generate contract tests for identity, network, data, failover, backup/restore, performance, quotas, and billing assumptions.
6. Run real target service or approved emulator evidence and compare source/target behavior.
7. Record maintenance ownership, deprecation, and exit plans.

## Required repository outputs

- Capability mapping records with evidence and status
- Target service configuration and adapter modules
- Data, compatibility, rollout, rollback, and operating model documents
- Negative, holdout, and cost test cases

## Verification

- Validate source and target service facts using provider APIs and runtime tests.
- Exercise P0 data path, failover or dependency failure, backup/restore, security, and cost scenario.
- Verify no hidden public endpoint, privilege expansion, retention loss, or unsupported quota assumption.
- Run independent representative workload.

## Stop and escalate when

- Target service cannot meet a P0 capability or regional/data requirement.
- Service facts are based only on documentation or names, not actual source configuration and workload.
- Migration would create irreversible data loss or an unowned operational burden.
- Cost or quota assumptions are unverified and material.

## Definition of done

- Each service has an explicit strategy, complete capability comparison, real target evidence, operational owner, migration/rollback plan, and support status.
- Critical service gaps are zero for certified scope.
