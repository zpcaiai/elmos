# Security, Privacy, and Financial Controls

## 1. High-risk assets

- Wallet and ledger balances
- Payment credentials and provider identifiers
- BYOK secret references
- Customer source-code-derived usage metadata
- Project contracts, invoices and tax identity
- Admin adjustment and refund capabilities
- Price books and vendor rate books

## 2. Mandatory controls

| Control | Minimum implementation |
|---|---|
| Tenant isolation | trusted server scope + DB/RLS or equivalent + cache/object/queue partitioning |
| Authentication | short-lived sessions/tokens, MFA for privileged roles |
| Authorization | RBAC + attributes; deny by default; resource ownership checks |
| Separation of duties | maker/checker for price activation, large refund, manual adjustment, key access |
| Secrets | secret manager, rotation, no logs/prompt/event/analytics exposure |
| Audit | append-only, actor/reason/before/after/approval/correlation, tamper evidence |
| Webhook | signature, timestamp window, environment, event uniqueness, payload hash |
| Idempotency | command-scoped unique keys and stored result replay |
| Encryption | transport, at rest, backups; field-level where risk requires |
| Fraud | velocity, device/account anomaly, refund abuse, credit farming, bot and takeover signals |

## 3. Data minimization

Usage events should carry technical resource metadata, not source code or prompts unless required and explicitly classified. Store hashes or references where possible. Apply separate retention windows for raw usage, aggregated finance facts, logs, evidence and legal records.

## 4. Privacy lifecycle

- Data inventory and purpose mapping
- Access/export with tenant verification
- Correction through new facts, not ledger deletion
- Deletion/anonymization where legally allowed
- Legal/financial hold exception with explicit scope and expiry
- Cross-region/data-residency controls for enterprise contracts

## 5. Fraud and abuse examples

- Repeated trial accounts or promotional-credit farming
- Concurrent reserve races designed to overspend
- Stolen payment instruments and rapid top-up/use/refund
- Forged or replayed webhook events
- Admin self-approval or suspicious manual adjustments
- BYOK secret probing or exfiltration
- Artificially triggering platform-fault refunds

Fraud decisions that affect access or money require reason codes, evidence and review/appeal paths appropriate to the risk.

## 6. Compliance disclaimer

This package defines engineering controls and evidence. It does not replace professional legal, tax, accounting, PCI, privacy or regulatory advice for the operating jurisdictions. Production activation requires the organization's approved policies.
