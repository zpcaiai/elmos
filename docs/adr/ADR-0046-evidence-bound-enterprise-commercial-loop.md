# ADR-0046: Evidence-bound enterprise commercial loop

## Status

Accepted for cross-language Batch 13 repository scope on 2026-07-21.

## Context

Batch 12 establishes an enterprise multi-tenant migration platform, but commercial delivery also spans qualification, discovery, POC, quoting, contracting, onboarding, delivery, support, customer success, partners and revenue operations. ELMOS already contains catalog, entitlement, order, onboarding, project, SLA, support, customer-success, asset and economic authorities. Duplicating them would create conflicting commercial truth. Letting an AI control plane mutate CRM, finance, partner or production systems would also make local test results indistinguishable from real business operations.

## Decision

Add `modules/commercial-loop` as an evidence-only EMCOM orchestrator and independent B13-A through B13-G adjudicator. Admit only an immutable, signed Batch 12 T-G artifact. Require all eight business domains, explicit normal and exceptional lifecycle states, and all six supported commercial motions.

Reuse V10 and `modules/commercial-operations` for existing business authorities. Add only missing evidence projections in V20, with organization ownership, forced RLS, source-system identity, versions, idempotency and append-only decision records. CRM, CPQ, contracts, billing, accounting, payment, support, partner settlement and production remain external systems of record.

Collect seven version-bound external evidence envelopes through narrow read-only authority ports. Evidence mismatch, absence, non-passing status, future observation or authority failure fails closed. Sanitize provider exceptions. Preserve failure and `NOT_RUN` states instead of smoothing them into aggregate success.

Make commercial readiness a structural invariant. `commercial_scale_ready` can be true only at B13-G with complete external evidence and zero blockers. Persist `commercial_operation_executed=false`. Write atomic, append-only artifacts outside the source repository and reject symbolic-link traversal.

## Consequences

Repository tests can prove deterministic gate policy, schema shape, exact report layout, compression and path safety. They cannot prove a customer was qualified, a POC succeeded, a contract was signed, access was granted, a project was accepted, billing occurred, an SLA was met, a customer renewed, a partner settled or a commercial operation scaled. Those facts remain `NOT_RUN` until the responsible external system supplies attributable evidence for the exact artifact version.
