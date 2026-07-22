---
name: unified-payment-intent-instruction-attempt-settlement-a-86fcf414
description: "Implement provider-neutral payment intents, instructions, attempts, authorizations, captures, settlements, returns and immutable cash movements."
---

# Unified Payment Intent Instruction Attempt Settlement And Cash Movement Domain

## Objective

Implement provider-neutral payment intents, instructions, attempts, authorizations, captures, settlements, returns and immutable cash movements.

This Skill belongs to **Batch 39B** and must extend the approved ELMOS financial domain rather than create parallel Tenant, Legal Entity, Contract, Invoice, Payment, Journal, Metric, Artifact, Policy, Case or Audit aggregates.

## Scope

Implement the domain model, lifecycle, APIs, provider adapters, policy controls, accounting or analytical reconciliation, audit evidence, observability, recovery paths and release gates required by this capability.

## Preconditions

1. Read the repository-level `AGENTS.md` and Batch 39 architecture documents.
2. Inventory existing financial aggregates, ledgers, contracts, provider integrations, tables, APIs, events and tests.
3. Verify authenticated Tenant and Legal Entity context, currency and period boundaries, audit/outbox, Artifact references and segregation of duties.
4. Write unresolved accounting, tax, payment-provider, banking, metric or planning assumptions to `docs/implementation/unified-payment-intent-instruction-attempt-settlement-a-86fcf414-baseline.md`.

## Required Capabilities

- Implement provider-neutral payment intents, instructions, attempts, authorizations, captures, settlements, returns and immutable cash movements.
- Reuse Batch 39A/39B facts and financial subledgers where relevant.
- Use immutable source facts and versioned calculations, policies, plans, forecasts, allocations and decisions.
- Keep provider-native payloads in adapters and normalized records in the core domain.
- Persist idempotency keys, source versions, monetary precision, currency basis, effective periods, decision inputs, receipts and reconciliation status.
- Expose operator-safe APIs and evidence-backed status; do not represent partial, unknown or unreconciled state as success.

## Required Artifacts

```text
unified_payment_intent_instruction_attempt_settlement_and_cash_movement_domain_manifest.json
unified_payment_intent_instruction_attempt_settlement_and_cash_movement_domain_decision.json
unified_payment_intent_instruction_attempt_settlement_and_cash_movement_domain_reconciliation.json
unified_payment_intent_instruction_attempt_settlement_and_cash_movement_domain_evidence.json
```

Every artifact must include Tenant, Legal Entity, subject, source/version, currency and period where applicable, policy/model version, timestamps, integrity digest, status, limitations and supporting evidence references.

## Workflow

1. Discover existing implementation and establish authoritative source facts.
2. Resolve Tenant, Legal Entity, accounting/planning entity, actor/workload, purpose, currency and period.
3. Create an immutable bounded input snapshot with exact contracts, policies, rates, provider versions and source digests.
4. Execute deterministic domain logic or an approved provider adapter.
5. Persist state and outbox atomically where financial state changes.
6. Reconcile external, distributed or accounting unknown results before retry, failover, close or publication.
7. Produce redacted immutable evidence, balanced accounting effects where applicable and operational telemetry.
8. Run negative, precision, idempotency, tenant-isolation, segregation, reconciliation, close and release-gate tests.

## Security and Financial Invariants

- Keep payment intent, instruction, attempt, provider observation, settlement and cash movement distinct.
- Provider timeouts and unknown results require reconciliation before retry or failover.
- Payment preparation, approval, release and reconciliation use segregated roles and scoped mandates.
- Protect PAN, bank-account identifiers, payment tokens, keys and prohibited authentication data at every boundary.
- Never persist API keys, bank credentials, card verification values, private keys or unredacted payment data.
- Active definitions and published financial versions are immutable; corrections use new versions, compensating records, legal correction documents or balanced journals.
- `UNKNOWN`, `INCONCLUSIVE`, `PARTIAL`, provider timeout and unreconciled differences do not imply success.
- Cross-tenant and cross-legal-entity authorization is checked at API, service, database, cache, event, export and Artifact boundaries.

## Implementation Requirements

- Add Flyway migrations with Tenant- and Legal-Entity-aware foreign keys, RLS where applicable, exact decimal columns, indexes and lifecycle constraints.
- Add domain services and ports/adapters without leaking provider DTOs into core modules.
- Add REST/OpenAPI or internal RPC contracts with idempotency, optimistic concurrency and explicit version fields.
- Add outbox events, audit records, metrics, traces, findings and operator-facing reconciliation status.
- Add source-to-result lineage, correction/version chains, provider receipt storage and controlled close/publication workflows.
- Add capability/version discovery instead of assuming a provider, standard, accounting or tax feature exists.

## Required Tests

```text
paymentIntentIsImmutable
unknownResultDoesNotBlindlyRetry
oneIntentCannotDuplicateSettlement
cashReceiptIsImmutable
lowConfidenceMatchRequiresReview
allocationReversalPreservesHistory
missingRequiredContextFailsClosed
duplicateRequestIsIdempotent
staleOrSupersededInputIsRejected
crossTenantAccessIsRejected
secretMaterialIsExcludedFromEvidence
releaseGateRejectsFabricatedSuccess
```

Also add domain-specific unit, migration, integration, provider-contract, property, reconciliation, security, chaos and scale tests.

## Verification

Run the repository-native build and test commands plus:

```bash
./validate.sh
```

Record exact commands, versions, output, skipped tests and reasons. Static package validation does not certify a tax jurisdiction, payment network, bank, accounting judgement or production close.

## Stop and Escalate

Stop and report `BLOCKED` when:

- authoritative source identity, Legal Entity, currency, accounting basis, period or stable financial subject cannot be established;
- required Tenant isolation, approval matrix, signer mandate or segregation of duties cannot be enforced;
- implementation requires floating-point authoritative amounts, plaintext secrets, TLS bypass, fail-open behaviour or destructive history rewrites;
- an external financial side effect cannot be made idempotent or reconciled;
- a mandatory tax, accounting, provider, policy, evidence, approval, close or integrity requirement is unavailable;
- passing requires weakening a security, accounting, reconciliation or financial-control invariant.

## Definition of Done

- Domain and lifecycle are implemented with immutable or versioned financial facts.
- Tenant, Legal Entity and resource authorization are enforced end to end.
- Monetary precision, currency, period and effective-date semantics are explicit.
- Provider capabilities, accounting assumptions and limitations are explicit.
- Idempotency, unknown-result reconciliation, corrections, recovery and period controls are tested.
- Results reconcile to their authoritative sources, subledgers, bank facts or General Ledger where applicable.
- Evidence is complete, integrity-protected, redacted and source-linked.
- APIs, migrations, events, observability and operational views are present.
- Negative, tenant-isolation, segregation, security and release-gate tests pass.

## Completion Report

Return:

1. architecture and reused aggregates;
2. domain tables, states, money/currency and period semantics;
3. APIs, events and provider adapters;
4. security, approval, accounting and policy controls;
5. reconciliations, evidence and operational telemetry;
6. exact tests and results;
7. files and migrations;
8. unresolved jurisdiction, provider, accounting or analytical limitations.
