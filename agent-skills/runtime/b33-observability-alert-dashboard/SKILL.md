---
name: b33-observability-alert-dashboard
description: "Migrate and certify metrics logs traces profiles business telemetry alerts dashboards retention sampling correlation SLO and incident evidence across cloud and runtime targets."
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

## Skill 1238: Observability, alert, and dashboard migration

## Use this skill when

- Monitoring, logging, tracing, alerts, dashboards, or SLOs must move providers or platforms.
- A target workload operates but cannot be diagnosed or measured against source behavior.
- Telemetry migration risks losing business context, retention, privacy, or alert semantics.

## Domain-specific risks and invariants

- Metric names alone do not preserve units, labels, aggregation, temporality, cardinality, sampling, retention, or alert behavior.
- Logs and traces can leak secrets and personal data.
- Alert routing, silence, escalation, and runbooks are operational contracts.

## Workflow

1. Inventory source metrics, logs, traces, profiles, business events, correlation, sampling, redaction, retention, dashboards, alerts, routing, SLOs, error budgets, and costs.
2. Define provider-neutral telemetry and SLO contracts with owners and data classifications.
3. Map target collectors, exporters, storage, sampling, schemas, dashboards, alert rules, notification routes, runbooks, and retention.
4. Instrument P0 workload and infrastructure resources with release, tenant, project, environment, and trace correlation.
5. Generate redaction and cardinality policies.
6. Run success/failure/latency/capacity scenarios; verify metrics, logs, traces, dashboards, alerts, routing, and SLO calculation.
7. Measure telemetry cost and test outage/degraded behavior.

## Required repository outputs

- Telemetry contracts and schema mapping
- Target collection/configuration, dashboards, alerts, SLOs, runbooks, retention, and redaction
- Runtime evidence for success and failure paths
- Cost and privacy evidence

## Verification

- Compare source and target business/technical signals for P0 scenarios.
- Trigger each critical alert safely and verify routing, deduplication, silence, recovery, and runbook.
- Scan telemetry for secrets and sensitive data.
- Verify SLO and error-budget calculations.

## Stop and escalate when

- P0 behavior cannot be observed or correlated.
- Telemetry requires storing prohibited data or unbounded high-cardinality labels.
- Critical alerts have no owner or response path.
- Retention/residency requirements cannot be met.

## Definition of done

- P0 workloads are diagnosable end to end; telemetry schemas, alerts, dashboards, SLOs, privacy, retention, routing, cost, and failure behavior are certified.
