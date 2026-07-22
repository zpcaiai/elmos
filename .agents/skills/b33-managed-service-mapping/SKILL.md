---
name: b33-managed-service-mapping
description: Map and migrate managed databases caches queues streams object stores search and other cloud services with data consistency identity network encryption backup recovery performance quota cost and cutover evidence.
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

## Skill 1236: Managed database, cache, queue, and storage mapping

## Use this skill when

- A managed data or messaging service must move provider, tier, region, engine, or operating model.
- An application modernization pack requires managed-service target decisions.
- Target configuration lacks data, availability, backup, performance, or quota validation.

## Domain-specific risks and invariants

- Managed services differ in APIs, consistency, availability, scaling, failover, backup, retention, encryption, networking, quotas, maintenance, observability, and pricing.
- A service name match is insufficient.
- Data migration and application contract migration must be coordinated.

## Workflow

1. Inventory source engine/service, version/tier, data size, access patterns, consistency, availability, regions/zones, backup, retention, encryption, network, identity, quotas, performance, maintenance, telemetry, and cost.
2. Define provider-neutral service and data contracts linked to Batch 31 database/data capabilities where applicable.
3. Evaluate target direct map, engine conversion, compatibility layer, self-managed, coexistence, or blocked strategy.
4. Implement target IaC, identity, network, backup, monitoring, alarms, scaling, and migration plan.
5. Run representative data/message/cache/storage workload, failure, backup/restore, quota, and performance tests.
6. Execute backfill/replication or test migration, consistency comparison, cutover rehearsal, and rollback.
7. Verify cleanup, retention, and deletion.

## Required repository outputs

- Managed-service capability matrix and target decision
- IaC, data migration/cutover, adapter, monitoring, and runbook artifacts
- Correctness, failure, restore, performance, quota, cost, and rollback evidence
- Holdout representative workload

## Verification

- Use real target service or approved local emulator only for capabilities it accurately represents.
- Compare P0 data/message/cache/object behavior and side effects.
- Exercise backup/restore or durable recovery and selected failover.
- Verify quotas and recurring cost with measured workload.

## Stop and escalate when

- Target cannot satisfy data durability, consistency, residency, backup, encryption, or availability requirements.
- A migration would truncate precision, ordering, retention, metadata, or message semantics.
- Cutover/rollback cannot preserve authoritative data.
- Operational ownership is missing.

## Definition of done

- Target service and migration strategy satisfy P0 functional, data, security, availability, recovery, performance, quota, cost, cutover, and lifecycle contracts with real evidence.
