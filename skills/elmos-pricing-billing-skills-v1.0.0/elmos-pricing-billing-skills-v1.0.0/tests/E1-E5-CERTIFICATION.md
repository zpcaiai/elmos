# E1–E5 Production Certification

## E1 — Static and package integrity

- Skill/frontmatter, manifests, schemas and checksums valid
- Lint/typecheck/build clean
- No secrets, floating money, direct balance mutation or dangerous migration pattern

## E2 — Unit, property and contract

- Domain state machines and policy tables
- Ledger, wallet, cap, refund and idempotency properties
- API/event/provider/migration contract tests

## E3 — Integrated financial flow

- Quote → reserve → run → usage → capture/release
- Subscription → invoice → payment → ledger
- Refund/dispute and reconciliation
- Enterprise/BYOK split billing

## E4 — Shadow, concurrency, security and resilience

- Old/new shadow rating difference explained
- High-concurrency reserve and webhook replay
- Chaos, crash recovery, queue redelivery, provider outage
- Cross-tenant and privileged-action red team
- Performance and backpressure under expected peak

## E5 — Production gate

- Canary criteria met
- Daily reconciliation clean or all differences owned
- SLO dashboards and alerts live
- Kill switch and rollback rehearsed
- Customer/support/finance runbooks ready
- Approvals and evidence package signed

No release may pass E5 with any duplicate charge, unbalanced ledger, unauthorized negative balance, hard-cap breach, cross-tenant exposure, secret leak, or unrecoverable data loss.
