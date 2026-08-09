---
name: b33-secret-config-environment
description: Migrate and certify secrets configuration environment overlays feature flags certificates and promotion semantics using references short-lived credentials encryption validation rotation and no plaintext leakage.
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

## Skill 1233: Secret, configuration, and environment migration

## Use this skill when

- Application or infrastructure configuration must move providers, formats, environments, or secret systems.
- Secrets are embedded in files, CI variables, templates, images, state, or runtime environments.
- Environment precedence, rotation, certificate, or feature-flag behavior is unclear.

## Domain-specific risks and invariants

- Configuration source precedence and reload semantics are runtime behavior.
- Secret names, versions, aliases, rotation, leases, and access policies matter as much as values.
- Environment promotion can introduce drift and hidden defaults.

## Workflow

1. Inventory configuration keys, sources, precedence, environment overlays, defaults, required values, secrets, certificates, keys, flags, reload, rotation, consumers, and data classification.
2. Define typed configuration and secret contracts without persisting secret values.
3. Map to target secret manager, KMS/HSM, workload identity, certificate service, parameter/config service, and feature-flag provider.
4. Generate references, short-lived access, validation, rotation, promotion, and rollback configuration.
5. Scan plans, state, logs, images, artifacts, CI, and model context for plaintext secrets.
6. Exercise missing/invalid config, secret rotation, certificate renewal, rollback, and environment promotion.
7. Verify deletion and revocation.

## Required repository outputs

- Configuration/secret inventory and typed contracts
- Target references, identities, rotation, validation, promotion, and rollback implementation
- Leak scans and lifecycle evidence
- Negative and holdout configuration cases

## Verification

- Run secret and credential scanning across generated outputs.
- Exercise rotation without downtime and verify old access revokes.
- Compare configuration precedence and failure behavior.
- Verify test/prod isolation and no secret value appears in plan, state, log, image, artifact, or prompt.

## Stop and escalate when

- Secret values cannot be removed from source control/history without an incident plan.
- Target cannot meet rotation, residency, HSM, or access requirements.
- Configuration precedence or reload semantics are unknown for a P0 workload.
- Migration would replace workload identity with long-lived static credentials.

## Definition of done

- All secrets use governed references and identities; configuration precedence, validation, promotion, rotation, revocation, and rollback are tested; plaintext leakage is zero.
