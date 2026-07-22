---
name: runner-assignment-offer-lease-ack-renew-cancel-and-reco-7837b31f
description: "Implement assignment offers, epochs, acknowledgements, leases, renewal, cancellation, completion, unknown-result reconciliation, and idempotency."
---

# Runner Assignment Offer Lease Ack Renew Cancel And Reconciliation

## Objective

Implement assignment offers, epochs, acknowledgements, leases, renewal, cancellation, completion, unknown-result reconciliation, and idempotency.

This Skill belongs to **Batch 36A** and must extend the approved ELMOS domain rather than create parallel Tenant, Identity, Artifact, Policy, Workflow, Audit, Contract or Finding aggregates.

## Scope

Implement the domain model, state transitions, APIs, provider adapters, policy enforcement, audit evidence, operational telemetry, recovery paths, tests and release gates required by this capability.

## Preconditions

1. Read the repository-level `AGENTS.md` and Batch 34–38 architecture documents.
2. Inventory existing aggregates, tables, APIs, events, providers and tests before editing.
3. Verify Tenant isolation, workload identity, audit/outbox and Artifact references.
4. Record unresolved provider/version assumptions in `docs/implementation/runner-assignment-offer-lease-ack-renew-cancel-and-reco-7837b31f-baseline.md`.

## Required Capabilities

- Implement assignment offers, epochs, acknowledgements, leases, renewal, cancellation, completion, unknown-result reconciliation, and idempotency.
- Use immutable or versioned facts for all security-, compliance-, repository-, execution- and finance-relevant state.
- Use typed commands and provider-neutral contracts; keep provider DTOs in adapters.
- Persist idempotency keys, source versions, decision inputs, receipts and reconciliation status.
- Expose operator-safe APIs and evidence-backed status; do not represent unknown state as success.

## Required Artifacts

```text
runner_assignment_offer_lease_ack_renew_cancel_and_reconciliation_manifest.json
runner_assignment_offer_lease_ack_renew_cancel_and_reconciliation_decision.json
runner_assignment_offer_lease_ack_renew_cancel_and_reconciliation_evidence.json
```

Artifacts must include tenant, subject, source/version, policy version, timestamps, integrity digest, status, limitations and supporting evidence references.

## Workflow

1. Discover and validate existing implementation and authoritative sources.
2. Resolve the authenticated Tenant, principal/workload, resource and purpose.
3. Create a bounded immutable input snapshot with exact versions and digests.
4. Execute deterministic domain logic or an approved provider adapter.
5. Persist result and outbox atomically where business state changes.
6. Reconcile external or distributed unknown results before retrying.
7. Produce redacted immutable evidence and operational telemetry.
8. Run negative, recovery, tenant-isolation and release-gate tests.

## Security and Correctness Invariants

- Bind every operation to assignment ID and epoch.
- Repository code is untrusted and executes only in approved sandboxes.
- Persist critical state locally before acknowledging it.
- Unknown results require reconciliation; cleanup failure is a security event.
- Never persist API keys, tokens, passwords, private keys or unredacted secrets.
- Active versions are immutable; corrections and changes create new versions or compensating records.
- `UNKNOWN`, `INDETERMINATE`, `PARTIAL` and provider timeouts do not imply success.
- Cross-tenant authorization is checked at API, service, database, cache, event and artifact boundaries.

## Implementation Requirements

- Add Flyway migrations with tenant-aware foreign keys, RLS where applicable, indexes and lifecycle constraints.
- Add domain services and ports/adapters without leaking provider-specific types into core modules.
- Add REST/OpenAPI or internal RPC contracts with idempotency and optimistic concurrency.
- Add outbox events, audit events, metrics, traces and operator-visible findings.
- Add lifecycle reconciliation, retry classification, cancellation and cleanup where applicable.
- Add capability/version discovery instead of assuming a provider feature exists.

## Required Tests

```text
happyPathUsesExactVersionedInputs
missingRequiredContextFailsClosed
duplicateRequestIsIdempotent
staleOrRevokedInputIsRejected
crossTenantAccessIsRejected
secretMaterialIsExcludedFromEvidence
unknownProviderResultRequiresReconciliation
releaseGateRejectsFabricatedSuccess
```

Also add domain-specific unit, integration, provider-contract, migration, property, security, chaos and scale tests described by the capability.

## Verification

Run the repository-native build and test commands plus:

```bash
./validate.sh
```

Record exact commands, versions, outputs, skipped tests and reasons. Static validation alone does not certify a production provider or customer environment.

## Stop and Escalate

Stop and report `BLOCKED` when:

- the authoritative source or stable subject identity cannot be established;
- the required Tenant boundary or segregation of duties cannot be enforced;
- the implementation requires plaintext secrets, TLS bypass, fail-open behaviour or destructive history rewrites;
- an external side effect cannot be made idempotent or reconciled;
- a mandatory policy, evidence, approval, compatibility or integrity requirement is unavailable;
- the only way to pass is to weaken a security or correctness invariant.

## Definition of Done

- Domain and lifecycle are implemented with immutable/versioned facts.
- Tenant and resource authorization are enforced end to end.
- Provider capabilities and limitations are explicit.
- Idempotency, retries, unknown-result reconciliation and recovery are tested.
- Evidence is complete, integrity-protected, redacted and source-linked.
- APIs, migrations, events, observability and operational views are present.
- Negative, tenant-isolation, security and release-gate tests pass.
- Completion report lists exact files, commands, results and unresolved limitations.

## Completion Report

Return:

1. architecture and reused aggregates;
2. domain tables and state machines;
3. APIs, events and provider adapters;
4. security and policy controls;
5. evidence and operational telemetry;
6. exact tests and results;
7. files and migrations;
8. limitations and blocked capabilities.
