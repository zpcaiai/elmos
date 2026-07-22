---
name: b33-serverless-event-runtime
description: "Migrate and certify serverless functions event sources triggers bindings concurrency retries idempotency timeouts cold starts state destinations dead letters schedules and deployment contracts."
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

## Skill 1235: Serverless function and event-driven runtime migration

## Use this skill when

- Functions, event triggers, bindings, queues, streams, schedules, or serverless workflows must move providers or runtime versions.
- A serverless target compiles but trigger, retry, concurrency, idempotency, or timeout behavior is unverified.
- Monolith logic is being extracted into event-driven functions.

## Domain-specific risks and invariants

- Provider event envelopes, batch semantics, partial failure, retry, concurrency, scaling, timeout, cold start, identity, networking, destinations, DLQ, and observability differ.
- At-least-once delivery can create duplicate business effects.
- Ephemeral runtime and deployment package limits affect compatibility.

## Workflow

1. Inventory exact runtime, function configuration, handlers, layers/extensions, triggers, event schemas, batch size/window, concurrency, scaling, retries, timeouts, destinations, DLQ, schedules, identities, network, storage, and telemetry.
2. Normalize event and execution contracts in Runtime Architecture and IaC IR.
3. Map target runtime, trigger, envelope, identity, network, configuration, packaging, concurrency, retry, idempotency, destination, and observability.
4. Generate adapters only for explicit event-envelope and provider differences.
5. Deploy in an isolated target environment and replay representative success, failure, duplicate, partial-batch, timeout, throttling, cold-start, and schedule scenarios.
6. Compare database/message/external side effects and cost.
7. Test version/alias rollout, canary, rollback, and destroy.

## Required repository outputs

- Target function/event IaC and code adapters
- Event, retry, idempotency, concurrency, timeout, and destination contracts
- Runtime replay, performance, cost, canary, rollback, and cleanup evidence
- Negative and holdout event corpora

## Verification

- Invoke real target functions through actual event sources where safe.
- Verify duplicates do not create uncontrolled business effects.
- Test partial batch, poison event, timeout, throttling, retry, DLQ/destination, and cancellation.
- Measure cold/warm latency and cost against profile.

## Stop and escalate when

- Idempotency cannot be established for retried writes.
- Provider trigger behavior or event envelope is unknown for P0 flows.
- Target limits cannot support required payload, duration, concurrency, or networking.
- Rollback/version routing cannot be controlled.

## Definition of done

- Certified event flows preserve trigger, payload, identity, retry, idempotency, concurrency, timeout, side effects, observability, rollout, rollback, and cost contracts.
