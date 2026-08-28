# Customer and Admin UX Specification

## 1. Quote card

Required fields:

- Task and frozen scope summary
- Repository size and planned file impact
- Mode: Economy / Balanced / Best Quality
- Estimated cost range and accepted hard cap
- Machine wall-clock ETA P50/P90
- Human-effort reference as a separate comparison
- Included tests, acceptance criteria and major exclusions
- Confidence and risk factors
- Price-book/quote expiry disclosure

Primary action: `Authorize and start`. Secondary actions: change mode, edit cap, refine scope, cancel.

## 2. In-run cost panel

- Actual posted usage
- Pending/unrated usage
- Reserved amount
- Predicted remaining amount and cap headroom
- Threshold markers and current alert state
- Current node, progress and machine ETA
- Actions: top up, downgrade, reduce scope, finish blockers only, stop and export

## 3. Wallet

Separate paid, promotional, reserved, consumed, refunded and expiring amounts. Explain deduction priority and expiry. Provide ledger-style history rather than only a mutable balance.

## 4. Invoice and usage detail

Start with understandable product lines, then allow drill-down to task/run/node/resource. Show `as_of`, pending status, currency, tax, discount, payment, refund and credit-note relationships.

## 5. Project contract

Display source commit/hash, requirement version, scope, cap/fixed price, milestones, tests, revisions, exclusions, third-party responsibilities, change orders, acceptance and settlement.

## 6. Admin controls

- Price book draft/review/activate/rollback
- Manual adjustment preview with balanced entries
- Refund eligibility and evidence
- Payment/reconciliation exception queue
- Tenant credit and budget controls
- Enterprise contract overrides
- Audit search

High-risk actions require reason, preview, reauthentication, independent approval and immutable audit.

## 7. Error language

Errors must say what happened, whether money moved, what is safe, what the system will do, and what the user can do. Never show a generic failure after a financial side effect without the authoritative status.
