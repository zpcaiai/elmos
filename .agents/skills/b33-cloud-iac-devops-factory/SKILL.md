---
name: b33-cloud-iac-devops-factory
description: Implement and certify an exact directional Cloud IaC and DevOps modernization pack with runtime discovery typed architecture contracts provider-neutral IaC IR real plan and apply evidence security drift cost rollback and cleanup.
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

## Skill 1223: Cloud, IaC, and DevOps modernization factory orchestrator

## Use this skill when

- A user asks to create or substantially expand a cloud, infrastructure-as-code, container, Kubernetes, CI/CD, or platform migration pack.
- An existing migration produces templates but lacks runtime inventory, target apply, security, drift, cost, rollback, cleanup, holdout, or representative workload evidence.
- Several Batch 33 domains must be coordinated into one production-shaped deployment slice.

## Domain-specific risks and invariants

- Cloud behavior is spread across source definitions, live resources, state, provider defaults, policies, identities, networks, managed services, pipelines, and runtime operations.
- A plan that succeeds can still expose data, broaden privilege, lose backups, break failover, orphan resources, or create unbounded cost.
- Provider-neutral intent and provider-specific implementation must remain distinct.

## Workflow

1. Inspect existing Batch 20-32 artifacts, live inventory, state, CI/CD, security and cost evidence; create `cloud-packs/<pack>/certification/gap-inventory.md`.
2. Confirm accountable, maintenance, cloud, security, network, data, SRE, and cost owners plus exact source/target tuples and one P0 workload.
3. Scaffold the pack if absent; implement static and runtime fingerprinting before any target generation.
4. Emit a typed Runtime Architecture Contract and provider-neutral IaC IR for the P0 workload, including identities, data flows, lifecycle, dependencies, policies, and source maps.
5. Select an exact target profile and implement deterministic mappings for container, orchestration, IaC, CI/CD, identity, network, managed services, ingress, observability, and security.
6. Run real source/target plans; apply to an approved isolated environment, exercise the P0 workload, inject a selected failure, verify rollback, and destroy all resources.
7. Run negative, holdout, and representative workloads. Fix systemic contract, IR, profile, module, or transformation defects.
8. Write security, drift, cost, lifecycle, maintainability, and certification evidence, then run the Batch 33 gate.

## Required repository outputs

- `cloud-packs/<pack-key>/pack.json`, `support-matrix.json`, and `source-fingerprint/fingerprint.json`
- `runtime-architecture/contract.json`, `iac-ir/model.json`, `target-profile/profile.json`, and `validation/validation-profile.json`
- `transformations/`, `adapters/`, `policies/`, `state/`, `rollout/`, `cost/`, `drift/`, and independent corpora
- `certification/{evidence.json,certification.json,gate-result.json,gate-report.md}`

## Verification

- Run the exact source and target IaC plan or equivalent validation with locked toolchains and provider plugins.
- Apply or emulate the P0 workload in an approved isolated environment; verify identity, network, DNS, secret, health, rollout, telemetry, security, cost, rollback, and destroy.
- Run pack, Runtime Architecture Contract, IaC IR, and conservative gate validators.
- Verify holdout and representative workloads pass without privilege broadening, secret embedding, ignored drift, widened budgets, or orphaned resources.

## Stop and escalate when

- No accountable owners, exact tuples, safe sandbox, source state, runtime inventory, or target provider profile exists.
- The proposed implementation relies on text replacement without typed contracts and resource semantics.
- A required capability would broaden IAM, public exposure, data movement, retention, or recovery without approval.
- Real apply or destroy cannot be executed safely and no approved emulator or integration environment can provide equivalent evidence.
- Critical unknowns, security regressions, drift, or orphaned resources remain.

## Definition of done

- One production-shaped workload has complete discovery, typed contracts, deterministic transformations, target plan/apply/runtime validation, rollback, cleanup, holdout, representative workload, and evidence.
- All critical security, network, data, lifecycle, and cost obligations are resolved or the pack remains non-certified.
- The conservative gate emits the strongest status supported by evidence.
