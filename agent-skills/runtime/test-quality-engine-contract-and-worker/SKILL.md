---
name: test-quality-engine-contract-and-worker
description: Define or operate the independent ELMOS Test Quality Engine contract, worker lifecycle, runner isolation, and fail-closed job semantics. Use for capabilities, discover/plan/generate/execute/evaluate APIs, test runner adapters, job cancellation, or quality-worker boundaries.
---

# Test Quality Engine Contract and Worker

## Establish the boundary

- Declare the engine as `ELMOS_TEST_QUALITY` version `1.0.0`.
- Support Java, .NET, Python, JavaScript/TypeScript, database, data/ML, infrastructure, client, and composite journeys through adapters.
- Keep tenant, workflow, risk, approval, evidence, audit, billing, and delivery in the shared control plane.
- Never let a worker edit a quality gate, approve a snapshot, promote an AI test, hide a flaky attempt, or accept business risk.

## Expose the contract

Implement `GET /engine/v1/capabilities`, `POST /discover`, `/plan`, `/generate`, `/execute`, `/evaluate`, job lookup, and cancellation. Require organization, immutable snapshot, workspace, correlation, profile, and idempotency identity. Scope idempotency and job visibility by tenant.

## Select runners safely

Choose only among Unit, Integration, Browser/Client, Data/ML, Performance, and Mutation runners. Require a rootless digest-pinned ephemeral workspace, namespace isolation, minimal permissions, default-deny network, no production secrets, explicit resource budgets, cancellation, and failing-evidence preservation. Require short-lived environment and test-data leases before execution.

## Fail closed

Return `NOT_RUN`, `INCONCLUSIVE`, or a structured failure when the adapter, runner, data, environment, scope, or evidence is unavailable. Keep evidence empty and `customerCodeExecuted=false`. Never convert missing, unknown, skipped, stale, or unexecuted work into success.

## Produce evidence

Bind every result to source commit, artifact digest, test identity, runner image digest, environment/data lease, tool version, selection graph, risk model, timestamps, attempts, and output hashes. Route quality decisions to an independent policy evaluator.
