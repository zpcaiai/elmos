---
name: b07-framework-migration-recipes-application-semantic-ob-11fafd73
description: "Implement observability and operational readiness for Batch 7: Framework Migration Recipes与Application Semantics."
---

# Objective

Implement logs, metrics, traces, health, SLOs, runbooks and operational ownership.

Apply this Skill to **Batch 7: Framework Migration Recipes与Application Semantics**. Treat the installed Batch manifest and repository evidence as authoritative; this normalized Skill must not invent unsupported provider, regulatory or runtime capabilities.

# Scope

- Batch: `7`
- Domain: `Framework Migration Recipes与Application Semantics`
- Role: `observability-and-operational-readiness`
- Edition: `normalized-implementation-edition`
- Source basis: recovered conversation architecture and manifest-driven compatibility where the original downloadable bundle was unavailable.

# Required Inputs

1. Exact repository commit and immutable source snapshot.
2. Installed Batch manifest, related SKILL.md files and dependency versions.
3. Current domain schemas, APIs, events, state machines and policy profiles.
4. Baseline build, test, security, performance and operational evidence.
5. Named owners for implementation, review and release.

# Workflow

1. Inspect the current repository before proposing changes.
2. Resolve Batch 7 dependencies and verify prerequisite gates.
3. Capture a no-change baseline and record pre-existing failures.
4. Build the smallest end-to-end vertical slice for `observability-and-operational-readiness`.
5. Preserve immutable inputs, source maps, versions and decision reasons.
6. Implement typed contracts and deterministic paths before AI or heuristic fallbacks.
7. Add idempotency, concurrency, timeout, cancellation and compensation handling where applicable.
8. Add tenant, authorization, privacy, secret and data-locality enforcement.
9. Execute required tests against representative and negative cases.
10. Generate an evidence pack and leave status at the strongest evidence-backed level.

# Required Invariants

- authentication, authorization, transactions and middleware order are preserved.
- framework mappings are contract-driven.
- unsupported semantics block promotion.

- Unknown, unsupported or unverified behavior remains explicit and blocks unsafe promotion.
- Active immutable versions are never edited in place; corrections create linked versions or compensating records.
- A green build, successful API call or dashboard status alone does not prove domain correctness.

# Required Tests

- happy-path representative vertical slice.
- invalid input and boundary values.
- duplicate request and idempotency.
- illegal state transition.
- cross-tenant and negative authorization.
- provider timeout or dependency failure.
- rollback, compensation and replay.
- evidence completeness and secret exclusion.

- Batch-specific property and conservation tests derived from the installed manifest.
- Performance and resource regression test for the critical path.
- Restart and recovery test proving durable state.

# Verification

Record exact commands, tool versions, environment identifiers, commit SHA, test counts, skipped tests, failures, waivers and artifact digests. Re-run the baseline and target paths from clean state. Verify that evidence references exist and are immutable.

# Stop and Escalate When

- the installed Batch manifest is missing or conflicts with this normalized description;
- a critical source contract, owner, legal interpretation or provider capability is unknown;
- implementation would require destructive history changes, secret exposure or tenant-boundary weakening;
- rollback, compensation or recovery cannot be demonstrated;
- test or evidence integrity cannot be established.

# Definition of Done

- typed contracts and lifecycle are implemented;
- critical invariants are executable tests;
- representative, negative, concurrency and recovery tests pass;
- open risks and unsupported cases are explicit;
- audit and evidence artifacts are generated;
- release status is derived from facts, not manually asserted.

# Completion Report

Return changed files, schema/API/event changes, state transitions, migration and rollback steps, exact test commands/results, performance measurements, security findings, evidence paths, waivers and unresolved blockers.
