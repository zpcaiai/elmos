---
name: b33-cloud-cost-capacity-optimizer
description: "Model validate and optimize cloud capacity availability quotas performance and recurring cost without weakening security durability recovery observability or workload contracts."
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

## Skill 1240: Cloud cost, capacity, and architecture optimization

## Use this skill when

- Target architecture needs sizing, quota, performance, resilience, or cost analysis.
- A migration has a successful plan but no evidence that the target is affordable or can carry peak load.
- Optimization candidates need safe validation.

## Domain-specific risks and invariants

- Cloud cost includes compute, data, storage, IOPS, requests, managed tiers, licenses, support, observability, backups, egress, idle capacity, and DR.
- Cheaper designs may reduce availability, security, recovery, or operational simplicity.
- Quota and regional capacity can block production regardless of theoretical sizing.

## Workflow

1. Collect source workload, peak, growth, resource, utilization, performance, availability, recovery, quota, and cost evidence.
2. Build a target capacity and cost model per environment, region, workload, DR, and migration period.
3. Identify right-sizing, autoscaling, schedule, storage tier, commitment, architecture, cache, data-transfer, and managed-service options.
4. Encode hard budgets, quotas, tags, TTL, ownership, and anomaly alerts.
5. Provision representative target capacity and run load, scale, failover, quota, and cost measurement scenarios.
6. Compare optimization options against P0 functional, security, availability, recovery, and operational contracts.
7. Record selected option, residual risk, forecast, and ongoing FinOps feedback.

## Required repository outputs

- Capacity model, quota inventory, cost model, budgets, tags, and forecasts
- Optimization decisions and IaC changes
- Load/scale/failover and measured cost evidence
- Cost anomaly and cleanup controls

## Verification

- Run representative and peak load tests with measured resource and service consumption.
- Validate autoscaling, quotas, headroom, failure capacity, and DR.
- Compare estimated and actual sandbox/test cost.
- Verify cost optimizations do not weaken required contracts.

## Stop and escalate when

- Required quota or regional capacity is unavailable.
- Cost estimate excludes material data-transfer, license, support, observability, backup, or DR cost.
- Optimization reduces P0 availability, security, durability, or recovery.
- No accountable budget owner exists.

## Definition of done

- Target sizing, quotas, peak/failure capacity, recurring/test cost, budgets, anomaly controls, and optimization tradeoffs are evidenced and approved.
