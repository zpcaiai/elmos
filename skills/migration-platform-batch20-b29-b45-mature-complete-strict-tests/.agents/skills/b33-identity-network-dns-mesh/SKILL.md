---
name: b33-identity-network-dns-mesh
description: Migrate and certify human workload and service identity network segmentation routing DNS certificates private connectivity egress ingress firewall load balancing and service mesh policies.
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

## Skill 1234: Identity, network, DNS, and service mesh migration

## Use this skill when

- Cloud identity, VPC/VNet, subnet, route, firewall, DNS, certificate, private endpoint, load balancer, or mesh migration is required.
- A target workload deploys but connectivity and trust boundaries are not proven.
- Cross-provider networking or identity mapping needs explicit validation.

## Domain-specific risks and invariants

- Network reachability alone does not prove least privilege, tenant isolation, private data paths, DNS correctness, mTLS, or failure behavior.
- IAM evaluation differs by provider and service.
- DNS TTL, certificate rotation, load balancing, NAT, egress, and mesh policy affect cutover and rollback.

## Workflow

1. Inventory human/workload identities, roles, policies, trust, network topology, CIDRs, routes, peering, gateways, firewalls, private endpoints, DNS zones/records, certificates, load balancers, service mesh, egress, and runtime flows.
2. Emit identity, network, connection, and policy contracts with data classification and source maps.
3. Design target least-privilege roles, trust, segmentation, private connectivity, DNS, certificate, ingress/egress, load balancing, and mesh policies.
4. Implement deterministic IaC and policy-as-code with explicit rule ownership.
5. Validate reachability and non-reachability, identity assumptions, DNS resolution, certificate rotation, mTLS, failover, and traffic policy.
6. Run attack/negative cases for privilege escalation, public exposure, cross-tenant access, DNS takeover, and egress bypass.
7. Exercise cutover and rollback with TTL and connection draining.

## Required repository outputs

- Identity and network contract maps
- Target IAM/network/DNS/mesh IaC and policies
- Reachability, denial, certificate, traffic, cutover, and rollback tests
- Security and data-path evidence

## Verification

- Use provider policy simulators plus real runtime identity and network tests.
- Verify required flows work and prohibited flows fail.
- Check no broad wildcard permissions or unintended public routes/endpoints.
- Exercise DNS/certificate rotation and selected failover.

## Stop and escalate when

- Source identity or network ownership is unknown.
- Target requires broader privilege or public exposure than approved.
- Overlapping CIDRs, data residency, or private connectivity cannot be resolved.
- DNS or certificate cutover lacks a safe rollback.

## Definition of done

- P0 identities and flows are least-privilege, private where required, source-mapped, tested for allow/deny, resilient to rotation/failure, and safe for cutover/rollback.
