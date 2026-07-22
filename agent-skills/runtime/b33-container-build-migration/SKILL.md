---
name: b33-container-build-migration
description: "Migrate and certify Dockerfiles container build graphs base images multi-stage builds package sources users files health checks entrypoints architectures SBOM signing provenance and runtime contracts."
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

## Skill 1227: Dockerfile and container build migration

## Use this skill when

- Dockerfile, container build, image base, registry, or build system modernization is required.
- An image builds but lacks reproducibility, non-root execution, multi-architecture, SBOM, signing, or runtime evidence.
- Legacy buildpacks or custom image pipelines need a certified target profile.

## Domain-specific risks and invariants

- Build context, `.dockerignore`, package repositories, generated files, architecture, entrypoint, signals, file ownership, and runtime dependencies affect behavior.
- A smaller image is not automatically safer or compatible.
- Changing base image, libc, architecture, or user can break native libraries and filesystem expectations.

## Workflow

1. Inventory Dockerfiles, build args, contexts, ignored files, base images, package managers, generated assets, secrets, architectures, registries, labels, users, ports, volumes, entrypoints, health checks, and runtime needs.
2. Lock base and builder images by digest and classify license, vulnerability, support, and architecture.
3. Emit container build contracts in Runtime Architecture and IaC IR.
4. Implement deterministic multi-stage target builds, secret mounts, cache scopes, non-root ownership, signal handling, and reproducible metadata.
5. Generate SBOM, vulnerability results, signatures, and provenance.
6. Build for required architectures and run P0 workload, health, shutdown, filesystem, network, and resource tests.
7. Push to an isolated registry, verify pull/deploy, then clean up.

## Required repository outputs

- Target Dockerfile/build definition and locked image manifest
- Container contract, SBOM, signature, provenance, vulnerability and license evidence
- Runtime and multi-architecture tests
- Negative fixtures for secret copying, root execution, mutable tags, and missing health checks

## Verification

- Run real container builds with cache disabled and enabled.
- Verify image digest reproducibility or explain approved nondeterminism.
- Run container as target UID/GID; test health, signals, read-only filesystem, resource limits, and required architecture.
- Scan, sign, verify, deploy, and remove test images/resources.

## Stop and escalate when

- A secret must be copied into an image or build log.
- Required native libraries or architecture cannot be validated.
- The only available base image is unmaintained or violates policy.
- Runtime requires privileged mode, host mounts, or broad capabilities without approval.

## Definition of done

- The target image builds reproducibly, is digest-pinned, non-root where required, supply-chain evidenced, runtime-compatible, tested on required architectures, and deployable/removable without secret leakage.
