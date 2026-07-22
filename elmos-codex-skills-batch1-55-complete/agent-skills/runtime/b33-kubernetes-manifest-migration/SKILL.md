---
name: b33-kubernetes-manifest-migration
description: "Migrate and certify Kubernetes workloads services configuration identity policy storage autoscaling rollout disruption health scheduling and lifecycle from exact source cluster versions to target profiles."
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

## Skill 1228: Kubernetes manifest and workload migration

## Use this skill when

- Kubernetes YAML, Kustomize output, operator-managed resources, or cluster workload modernization is required.
- A workload must move between cluster distributions, versions, regions, or providers.
- Existing manifests lack policy, rollout, disruption, health, or runtime verification.

## Domain-specific risks and invariants

- API compatibility alone does not preserve storage, ingress, identity, networking, scheduling, disruption, autoscaling, or operator behavior.
- Admission mutation and cluster defaults can materially change deployed resources.
- Cluster version, CNI, CSI, ingress, service mesh, policy engine, and operators are part of the tuple.

## Workflow

1. Discover rendered manifests and live objects, owners, admission mutations, CRDs, operators, namespaces, service accounts, RBAC, network policies, storage classes, ingress, probes, resources, autoscaling, disruption budgets, topology, and rollout behavior.
2. Normalize objects into IaC IR and Runtime Architecture Contract while preserving Kubernetes-specific extensions.
3. Map deprecated/removed APIs and target cluster capabilities using exact versions.
4. Generate target manifests or modules with workload identity, secrets references, health, resources, policies, storage, rollout, and topology constraints.
5. Validate server-side dry-run, schema, admission, policy, and diff.
6. Deploy to an isolated target cluster; exercise P0 traffic, rollout, scaling, eviction, node failure, secret rotation, and shutdown.
7. Delete the namespace/resources and verify no cluster-scoped or cloud resources remain.

## Required repository outputs

- Rendered target manifests and resource ownership map
- Cluster capability profile and admission/operator inventory
- Policy, rollout, storage, networking, autoscaling, disruption, and runtime evidence
- Negative and holdout workloads

## Verification

- Run exact target cluster server-side validation and policy checks.
- Compare desired, admitted, and live objects.
- Run rollout, health, scale, restart, selected failure, and rollback tests.
- Verify cleanup of namespaced, cluster-scoped, load-balancer, volume, DNS, and identity resources.

## Stop and escalate when

- Required CRD/operator behavior is unknown or unavailable.
- Migration would remove network policy, workload identity, encryption, storage durability, or disruption protection.
- Admission changes cannot be reproduced or inspected.
- Test cleanup cannot safely remove cloud-integrated resources.

## Definition of done

- P0 workloads deploy and operate on the exact target cluster profile with policy, identity, network, storage, rollout, scaling, recovery, and cleanup evidence.
- No silent API or operator behavior loss remains.
