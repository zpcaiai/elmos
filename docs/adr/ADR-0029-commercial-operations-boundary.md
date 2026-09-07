# ADR-0029: Commercial operations and asset reuse boundary

- Status: Accepted
- Date: 2026-07-21

## Decision

ELMOS introduces a framework-free `commercial-operations` domain and a separate `commercial-api` boundary. Stable feature keys and versioned Entitlement decisions control runtime commercial rights; edition names and prices do not appear as authorization conditionals. Security and contract restrictions outrank entitlement, and quota, internal cost, customer charge and formal accounting remain distinct.

Accepted orders generate idempotent subscriptions, entitlements, credits and explicit fulfillment tasks. Partial fulfillment is a first-class status. Onboarding readiness gates formal migration, project health uses weighted facts and cannot hide failed critical gates, and scope changes require explicit recalculation. SLA measurement, support severity, marketplace certification, knowledge trust, customer health and commercial metrics all retain evidence references and missing-data status.

CRM, payment collection, tax, formal invoices, general ledger, revenue recognition and enterprise procurement remain external systems behind Ports. ELMOS may prepare requests and reconciliation evidence but does not claim those financial effects.

## Consequences

Commercial behavior is testable without external commercial providers. Live contracts, payment state, invoice adjustments, customer notifications, production marketplace distribution and financial reconciliation remain external acceptance gates. Customer source, private assets and knowledge are not exposed to commercial or support roles merely because an order or ticket exists.
