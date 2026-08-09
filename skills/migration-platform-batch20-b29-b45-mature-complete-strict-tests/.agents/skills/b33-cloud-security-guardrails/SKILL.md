---
name: b33-cloud-security-guardrails
description: Migrate and certify cloud security policies IAM boundaries network controls encryption keys admission policies compliance guardrails detective controls exceptions and remediation without privilege expansion.
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

## Skill 1239: Cloud security policy and guardrail migration

## Use this skill when

- IAM, policy-as-code, organization policy, network guardrail, encryption, admission, compliance, or detective control migration is required.
- A target architecture lacks enforceable baseline security.
- Provider policy semantics or exception workflows need comparison.

## Domain-specific risks and invariants

- Policy engines and IAM evaluation differ by provider and resource.
- A syntactically similar policy may grant broader access.
- Preventive, detective, and corrective controls must remain connected to owners and evidence.

## Workflow

1. Inventory source policies, roles, trust, permissions, boundaries, organization controls, network guardrails, encryption/KMS, key policies, admission, vulnerability, audit, detective rules, exceptions, and remediation.
2. Map control objectives to provider-neutral policy contracts and exact target enforcement mechanisms.
3. Generate least-privilege roles, boundaries, deny controls, network policies, encryption, logging, admission, and detective rules.
4. Use policy simulators/static analyzers plus real allow/deny tests.
5. Test exception request, approval, expiry, compensating controls, and revocation.
6. Run negative/attack cases for escalation, confused deputy, public exposure, unencrypted data, disabled logs, and policy bypass.
7. Emit control crosswalk and evidence.

## Required repository outputs

- Control and policy contract maps
- Target policy-as-code and enforcement resources
- Allow/deny, exception, expiry, detection, remediation, and audit evidence
- Security regression corpus

## Verification

- Run policy unit tests, provider validation/simulation, and real isolated principal/resource tests.
- Verify expected access works and prohibited access fails.
- Check no wildcard/broad role, public exposure, unencrypted sensitive resource, or disabled audit was introduced.
- Exercise exception expiry and remediation.

## Stop and escalate when

- Target provider cannot enforce a mandatory control.
- Required access can only be achieved through unapproved broad permissions.
- Policy semantics are unknown for a P0 path.
- Critical exception lacks owner, expiry, or compensating control.

## Definition of done

- Mandatory controls are mapped, enforced, tested, auditable, least-privilege, and free of critical regressions; exceptions are bounded and governable.
