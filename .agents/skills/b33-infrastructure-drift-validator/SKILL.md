---
name: b33-infrastructure-drift-validator
description: Detect reconcile and verify drift among source definitions live resources IaC state target plans deployments pipelines policies cost and runtime contracts without silently adopting or destroying unknown resources.
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

## Skill 1241: Infrastructure drift and source-target validation

## Use this skill when

- IaC definitions, state, and live resources may disagree.
- A migration must import, move, coexist with, or replace manually managed infrastructure.
- Target deployment requires continuous drift and conformance validation.

## Domain-specific risks and invariants

- Drift can be legitimate emergency change, unmanaged resource, provider default, policy mutation, incident workaround, or unauthorized change.
- Blind refresh/apply can adopt or destroy the wrong resource.
- Desired-state equality is insufficient without runtime-contract validation.

## Workflow

1. Collect source definitions, live source inventory, source state, target definitions, target plan, target state, live target inventory, policy results, runtime contract observations, and cost inventory.
2. Normalize identities and classify drift as expected, imported, manual-approved, emergency, provider-default, stale state, unauthorized, orphan, missing, or unknown.
3. Create explicit import, moved, retain, replace, revert, adopt, or investigate decisions with owners.
4. Implement deterministic drift checks in CI and scheduled operations.
5. Validate that target plan converges without unapproved replacement or deletion.
6. Apply selected reconciliation in isolation or controlled target environment and verify runtime contracts.
7. Test delete/destroy cleanup and report orphaned resources and costs.

## Required repository outputs

- Drift inventory and decisions
- Import/move/ownership/reconciliation plans
- CI/scheduled drift checks and policy rules
- Convergence, runtime, cleanup, and cost evidence

## Verification

- Run provider-native drift/what-if/refresh plus independent live inventory comparison.
- Compare state addresses, live IDs, ownership tags, policies, runtime contracts, and costs.
- Exercise an expected and unauthorized drift case.
- Verify cleanup and no orphaned resources after test.

## Stop and escalate when

- Live resource identity or ownership is ambiguous.
- An apply would delete or replace protected resources.
- Unknown drift affects P0 identity, network, data, or security.
- State lock, backup, or recovery is unavailable.

## Definition of done

- All P0 resources have known ownership and drift classification; convergence is safe, unauthorized drift is detected, imports/moves are tested, and orphan count is zero.
