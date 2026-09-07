---
name: b33-cloud-certification-gate
description: "Run the conservative Batch 33 certification gate and emit certified limited experimental or blocked status from exact tuples fingerprints typed contracts real plan apply runtime security drift cost rollback cleanup holdout and evidence."
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

## Skill 1242: Batch 33 Cloud, IaC, and DevOps certification gate

## Use this skill when

- A Cloud Pack is ready for formal readiness evaluation.
- A pack status or support capability is being promoted.
- Release, customer support, or marketing claims need evidence-backed status.

## Domain-specific risks and invariants

- Certification must resist status-file edits and placeholder evidence.
- A successful plan or deployment alone does not prove security, data, lifecycle, rollback, drift, cost, or cleanup.
- Each exact tuple and capability needs independent evidence.

## Workflow

1. Run structural validation for pack, support matrix, source fingerprint, Runtime Architecture Contract, IaC IR, target profile, validation profile, and certification files.
2. Verify exact source/target tuple, owners, source/runtime evidence, source mapping, target profile, corpus separation, and real evidence references.
3. Run real source/target plan checks and applicable target apply/runtime validation.
4. Verify P0 deployment contracts, container/orchestrator/CI/CD, identity/network, secret/config, observability, security, cost, drift, rollback, destroy, and representative workloads.
5. Check zero-tolerance fields for unknowns, silent drops, privilege/network/data/security regressions, secret leaks, drift, orphans, budget violations, destroy failures, and test-integrity violations.
6. Verify holdout and representative workload artifacts are non-empty and independent.
7. Write gate result/report and keep or downgrade status to the strongest evidence-supported level.

## Required repository outputs

- `certification/gate-result.json`
- `certification/gate-report.md`
- Updated evidence/certification records only when supported
- Explicit blockers and conditions for non-certified packs

## Verification

- Run `validate_cloud_pack.py`, `validate_runtime_contract.py`, `validate_iac_ir.py`, and `run_cloud_gate.py`.
- Independently inspect evidence refs and command outputs.
- Attempt fake certification and confirm the gate rejects it.
- Confirm a changed tuple, policy, provider, region, tool version, state backend, or critical service triggers recertification.

## Stop and escalate when

- Any exact tuple or owner is unset.
- Real source/target plan or applicable runtime evidence is missing.
- Critical unknown, silent drop, security/network/data regression, secret leak, drift, orphan, or cleanup failure remains.
- Holdout or representative workload is absent.
- Evidence files are placeholders, missing, or do not bind to the certified tuple.

## Definition of done

- Gate output is reproducible, conservative, evidence-backed, and cannot be bypassed by editing status fields.
- Only packs satisfying all certified thresholds and zero-tolerance requirements receive certified status.
