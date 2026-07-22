---
name: b37-commercial-license-billing-revenue-share
description: "Implement marketplace commercial licensing entitlements metering billing refunds taxes payouts revenue share and financial reconciliation without granting commercial systems authority over security gates."
---

# Skill 1323: b37-commercial-license-billing-revenue-share

## Use this skill when

- Paid extensions or revenue sharing are required.
- Publisher and customer financial obligations need automation.

## Domain-specific risks and invariants

- Incorrect entitlements can expose paid or restricted capabilities.
- Billing events can be duplicated or manipulated by extensions.

## Workflow

1. Define free, paid, subscription, usage, seat, tenant, private, trial, and enterprise licensing models.
2. Implement signed entitlement tokens and offline leases.
3. Collect trusted platform-side metering with idempotency and dispute evidence.
4. Implement invoices, credits, refunds, taxes, payout holds, revenue share, currency, and reconciliation.
5. Separate commercial approval from technical and security certification.

## Required repository outputs

- commercial policy and price versions
- entitlement and metering contracts
- billing payout refund and reconciliation records

## Verification

- Test duplicate, delayed, missing, forged, and corrected meter events.
- Verify expired or revoked entitlements fail safely without data loss.
- Reconcile customer charges, platform ledger, and publisher payout.

## Stop and escalate when

- Tax, payout, legal, or refund requirements are unresolved.
- Metering depends solely on extension-reported values.

## Definition of done

- Entitlements and billing are deterministic and auditable.
- Financial discrepancies have a controlled resolution path.
- Commercial status cannot bypass security.
