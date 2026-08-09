---
name: b33-cicd-pipeline-migration
description: Migrate and certify Jenkins GitHub Actions GitLab CI Azure DevOps and other CI CD pipelines including triggers permissions environments artifacts caches approvals deployment provenance rollback and secret boundaries.
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

## Skill 1232: CI/CD pipeline migration

## Use this skill when

- A build or deployment pipeline must move providers, modernize, or standardize.
- Pipeline behavior is only described in scripts and lacks typed stages, permissions, approvals, artifacts, or rollback contracts.
- A migrated pipeline builds but has not proven secure promotion and release behavior.

## Domain-specific risks and invariants

- CI/CD behavior includes triggers, event filters, branch protection, identity, secret scopes, caches, artifacts, matrix, environment approvals, concurrency, deployment, provenance, and rollback.
- Equivalent syntax does not imply equivalent security or release process.
- Third-party actions/plugins are supply-chain dependencies.

## Workflow

1. Inventory exact server/provider versions, plugins/actions/tasks, triggers, branches, matrices, agents/runners, credentials, caches, artifacts, environments, approvals, deployments, notifications, retries, concurrency, and post actions.
2. Model stages, dependencies, inputs/outputs, identities, policies, and release contracts in Runtime Architecture and IaC IR extensions.
3. Generate target pipeline with pinned actions/tasks/images, workload identity or short-lived credentials, protected environments, deterministic artifacts, SBOM/signing/provenance, and explicit rollback.
4. Migrate caches and artifacts without cross-branch or cross-tenant contamination.
5. Run pull-request, main, release, failure, retry, approval, cancellation, and rollback paths in an isolated target project.
6. Compare artifact digests, status checks, permissions, evidence, and deployment results.
7. Document plugin/action replacement and maintenance owners.

## Required repository outputs

- Target pipeline definitions and exact dependency locks
- Trigger, permission, environment, artifact, cache, promotion, rollback, and provenance contracts
- End-to-end CI/CD run evidence
- Negative and holdout pipeline cases

## Verification

- Run real target CI/CD jobs or an approved local runner with equivalent identity and policy.
- Verify untrusted PRs cannot access deployment secrets.
- Verify environment approval, artifact immutability, promotion, cancellation, failure cleanup, and rollback.
- Scan third-party actions/plugins and verify pinning/signatures where supported.

## Stop and escalate when

- Migration would expose secrets to untrusted branches or forks.
- Required plugin behavior is unknown or unmaintained.
- Target provider cannot enforce required approvals or identity boundaries.
- Pipeline success depends on mutable actions/images or manual undocumented state.

## Definition of done

- Target pipeline preserves triggers, permissions, artifacts, gates, promotion, rollback, supply-chain evidence, and failure cleanup with real runs and zero secret leaks.
