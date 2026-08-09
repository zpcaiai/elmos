---
name: b33-runtime-architecture-contract
description: Implement or extend the typed Runtime Architecture Contract for components identities connections data flows dependencies lifecycle scaling availability rollout health recovery observability policies and source mapping before cloud transformation.
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

## Skill 1224: Runtime Architecture and Deployment Contract model

## Use this skill when

- Runtime topology or deployment behavior must be discovered, normalized, compared, or generated.
- A migration has IaC files but no explicit model of workload behavior, identity, data flow, availability, rollout, or recovery.
- Cloud service mappings require provider-neutral runtime intent.

## Domain-specific risks and invariants

- Templates rarely reveal all runtime dependencies, hidden identities, manually configured DNS, autoscaling, failover, or data movement.
- Resource equivalence does not imply workload equivalence.
- Connections and identities must be first-class; otherwise least privilege and network boundaries cannot be verified.

## Workflow

1. Inventory source components, runtimes, processes, containers, functions, jobs, managed services, identities, endpoints, data stores, and operational dependencies.
2. Capture live topology, traffic, health, scaling, zones, failover, backup, retention, and runtime policy evidence.
3. Define stable node IDs and emit components, connections, identities, data flows, policies, obligations, and source maps.
4. Model required availability, startup, shutdown, rollout, rollback, scaling, recovery, data classification, and SLO contracts.
5. Link Runtime Architecture nodes to IaC IR resources and source definitions without embedding provider-specific implementation in core intent.
6. Add validator tests for duplicate IDs, unknown references, missing source maps, cycles that violate lifecycle, and unowned P0 nodes.
7. Use the contract to drive one target mapping and runtime comparison.

## Required repository outputs

- Typed contract schema and validator updates
- A populated `runtime-architecture/contract.json` with source map
- Contract-to-IaC and contract-to-runtime evidence links
- Negative and holdout fixtures for invalid topology and missing identities

## Verification

- Run `validate_runtime_contract.py`.
- Compare the model against source live inventory and target runtime observations.
- Verify every P0 component, identity, connection, and data flow has source evidence and target mapping.
- Exercise startup, health, scaling, selected failover, and shutdown contracts.

## Stop and escalate when

- Runtime inventory is inaccessible and static definitions are known incomplete.
- Critical data flows, identities, network paths, or state ownership cannot be determined.
- The model would collapse provider-specific limitations into false equivalence.
- Source maps or accountable owners are missing for P0 nodes.

## Definition of done

- The contract is schema-valid, referentially complete, source-mapped, owner-reviewed, linked to IaC IR, and exercised against source and target runtime evidence.
- Unknown P0 architecture behavior is zero or the pack is blocked/limited.
