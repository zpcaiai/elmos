---
name: b38-platform-version-compatibility-matrix
description: Maintain exact product, API, database, workflow, extension and runner compatibility across supported versions.
---

# Skill 1338: b38-platform-version-compatibility-matrix

## Use this skill when

- Implementing or reviewing **Platform version compatibility matrix** within Batch 38: 企业部署矩阵与升级生命周期.
- A repository needs production-shaped implementation, negative tests, holdout evidence and a conservative certification decision rather than a design-only document.

## Required context

- Read repository `AGENTS.md`, relevant Batch 21–37 contracts, current edition/route/version manifests, and existing policies before editing.
- Resolve accountable owners for product, engineering, security, operations, finance, legal and customer acceptance where applicable.
- Lock exact source commit, target commit, artifact digest, environment digest, tool versions and policy bundle.

## Domain-specific invariants

- Version claims bind exact source, target, protocol, schema and artifact digests; floating versions are prohibited.
- Upgrade success requires mixed-version operation, rollback and data-compatibility evidence.
- Never edit certification status, Golden data, tolerance, evidence files or tests merely to make a gate pass.
- Every accepted claim must resolve to immutable evidence and an executable replay or independent verification path.

## Workflow

1. Inspect current implementation and create a gap inventory mapped to the Batch 38 support matrix and strict-test coverage.
2. Define the typed contract, state machine, ownership, policy decisions, failure modes, compatibility boundaries and lifecycle for **Platform version compatibility matrix**.
3. Implement the smallest complete production-shaped vertical slice using deterministic mechanisms first; use bounded agents only for explicitly approved long-tail work.
4. Add success, boundary, malformed-input, security, dependency-failure, replay/idempotency, version-drift and evidence-tampering tests.
5. Execute real tools, runtimes, editions, providers or independent review when the claim cannot be established by unit tests.
6. Run development and negative corpora, then untouched holdout and representative workloads. Preserve all failures and minimized replay cases.
7. Update evidence and run the conservative Batch 38 gate. Keep the strongest status actually supported by evidence.

## Required repository outputs

- `deployment-lifecycle-packs/<pack-key>/pack.json` and versioned support matrix
- typed domain profiles, policies, state machines and immutable evidence records
- development, negative, untouched holdout and representative production-shaped corpora
- conservative gate result and human-readable evidence report

## Verification

- Run `python3 scripts/batch38/validate_skill_bundle.py .`.
- Run the Batch 38 pack validator and final gate against the exact pack directory.
- Verify each evidence reference exists, matches its SHA-256 digest and is bound to the claimed artifact and environment.
- Re-run the relevant Batch 1–37 strict test skills and all affected integration tests.

## Stop and escalate when

- An exact owner, version, artifact, environment, customer boundary, legal basis or rollback path is missing.
- A P0 claim depends only on mocks, generated prose, self-attestation, edited Golden data or an unreviewed waiver.
- The implementation would weaken tenant isolation, security, test integrity, data correctness, service recovery or financial reconciliation.
- Required real infrastructure, customer evidence or independent assessment is unavailable; record the claim as blocked rather than fabricating evidence.

## Definition of done

- The typed implementation and lifecycle are integrated with existing control-plane, runner, evidence, policy and workflow contracts.
- Negative and adversarial tests prove prohibited paths fail closed.
- Untouched holdout and representative workloads pass the approved profile with no unresolved P0 unknowns.
- The Batch 38 gate emits only the strongest evidence-supported status and produces a reviewable failure report otherwise.
