---
name: b33-provider-neutral-iac-ir
description: Implement or extend a provider-neutral typed IaC IR for resources modules variables outputs policies dependencies lifecycle identity data classification state ownership and source mapping before infrastructure generation.
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

## Skill 1225: Provider-neutral IaC IR and resource model

## Use this skill when

- Source IaC must be parsed into a common model.
- A new IaC language, cloud-native template, Kubernetes manifest, Helm chart, or Terraform target must be supported.
- Cross-provider or cross-tool transformations need stable resource semantics.

## Domain-specific risks and invariants

- Raw HCL, YAML, JSON, DSL, and pipeline syntax cannot safely serve as the common semantic model.
- Provider lifecycle, replacement, dependency, import, and state behavior must not be erased.
- A provider-neutral IR needs extension points rather than pretending every service is identical.

## Workflow

1. Inventory source constructs, modules, expressions, variables, outputs, providers, state addresses, dependencies, lifecycle rules, policies, and generated values.
2. Define stable IR resource IDs and provider-neutral types for compute, container, network, identity, data, messaging, storage, DNS, gateway, observability, and policy.
3. Preserve source expressions as typed values or explicit unresolved obligations; do not flatten unknown expressions into strings.
4. Model create/update/replace/delete/import/move behavior, state ownership, secrets, data classification, encryption, and dependencies.
5. Add provider-specific extension records for capabilities not expressible in the core model.
6. Implement source-map, reference, dependency-cycle, obligation, and lifecycle validation.
7. Generate one target representation and compare target plan against IR intent.

## Required repository outputs

- IaC IR schema, types, adapters, validators, and test fixtures
- `iac-ir/model.json` with stable IDs and source map
- Source and target adapter conformance tests
- Negative cases for unknown references, unsafe replacement, secret literals, and silent resource loss

## Verification

- Run `validate_iac_ir.py`.
- Round-trip a representative resource graph through source adapter, IR, and target emitter.
- Compare target plan resources, dependencies, lifecycle, identity, network, encryption, and outputs against IR.
- Run holdout constructs not used to author mappings.

## Stop and escalate when

- The only available strategy is regex/string replacement.
- Source expressions, state addresses, lifecycle, identities, or data-classification semantics cannot be represented.
- Generation would silently drop a resource or policy.
- Provider-specific behavior is incorrectly claimed as portable.

## Definition of done

- IR is typed, referentially valid, source-mapped, extension-capable, and drives a target plan without silent drops or unsafe lifecycle changes.
- Adapter/emitter conformance and holdout tests pass.
