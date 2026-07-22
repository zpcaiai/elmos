---
name: b37-commercial-settlement-refund-tax-fraud
description: "Implement commercial period close metering reconciliation invoices refunds credits chargebacks taxes payouts revenue share fraud controls and ledger audit."
---

# Skill B37-X14: b37-commercial-settlement-refund-tax-fraud

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Extension-reported usage is never the sole billing authority.
- Financial adjustment never modifies original ledger events.
- Security quarantine can stop entitlement without deleting financial evidence.

## Workflow

1. Lock the settlement period and collect platform-authoritative idempotent meter events.
2. Reconcile usage, entitlements, invoices, credits, refunds, chargebacks, taxes, fees, revenue share, and publisher payouts.
3. Detect duplicate meters, self-dealing, synthetic usage, refund abuse, stolen payment, payout diversion, and sanctioned recipient risks.
4. Require separation of duties and signed approval for period close, adjustment, and payout.
5. Produce customer, publisher, finance, tax, and audit statements and preserve correction history.

## Required repository outputs

- `commercial/settlement.json`
- meter reconciliation, invoices, refunds, taxes, payouts, fraud cases, approvals, and audit evidence

## Verification

- Run `validate_commercial_settlement.py`.
- Reconcile a representative period including refund, chargeback, tax, payout, and correction scenarios.

## Stop and escalate when

- Settlement difference is non-zero or payout identity is unverified.
- Fraud, sanctions, tax, or separation-of-duties findings remain open.

## Definition of done

- Settlement closes to zero difference with approved refunds, taxes, payouts, fraud controls, and immutable audit history.
