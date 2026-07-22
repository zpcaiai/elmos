---
name: b33-api-gateway-ingress-traffic
description: "Migrate and certify API gateways ingress load balancers routes domains certificates authentication authorization rate limits transformations canary traffic health and rollback behavior."
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

## Skill 1237: API gateway, ingress, and traffic strategy migration

## Use this skill when

- API gateway, ingress controller, load balancer, DNS, edge policy, or traffic-routing migration is required.
- A target endpoint exists but route, auth, rate limit, timeout, canary, health, or rollback behavior is unverified.
- Strangler/coexistence requires controlled traffic.

## Domain-specific risks and invariants

- Gateways encode public contracts, security, request/response transforms, quotas, retry, timeout, health, TLS, and rollout behavior.
- Route precedence and default backends can create exposure or misrouting.
- Canary traffic must not duplicate unsafe side effects.

## Workflow

1. Inventory domains, certificates, routes, methods, hosts, headers, transforms, auth, authorization, WAF, quotas, rate limits, retry, timeout, CORS, caching, health, backends, canary, logging, and DNS.
2. Emit gateway and traffic contracts linked to API contracts from earlier batches.
3. Map to exact target gateway/ingress/load-balancer profile and generate deterministic routes and policies.
4. Implement certificates, identity, private/public boundaries, health, observability, canary, connection draining, and rollback.
5. Run positive and negative route, auth, quota, timeout, WAF, body-size, streaming, and default-route tests.
6. Execute shadow/canary with safe side-effect controls and progressive ramp.
7. Rehearse DNS/route rollback and certificate rotation.

## Required repository outputs

- Target gateway/ingress IaC and route contract
- Security, quota, transform, health, canary, DNS, certificate, and rollback evidence
- Route matrix and caller migration plan
- Negative and holdout traffic cases

## Verification

- Compare source/target routes, responses, headers, errors, auth, and side effects.
- Verify unknown hosts/routes fail safely.
- Exercise rate limit, timeout, body/stream limits, health removal, canary stop, and rollback.
- Check public exposure and certificate policy.

## Stop and escalate when

- Target cannot preserve required auth, private connectivity, streaming, payload, or routing behavior.
- Canary would produce duplicate irreversible effects.
- Default route or DNS behavior could expose an unintended service.
- Certificate or rollback ownership is missing.

## Definition of done

- P0 traffic contracts, security, quotas, health, canary, DNS/certificate, observability, and rollback are validated with zero unintended exposure or duplicate side effects.
