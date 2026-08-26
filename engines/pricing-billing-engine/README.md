# ELMOS pricing and billing reference engine

This package supplies deterministic, executable **local reference behavior** for
the 18 pricing and billing Skill domains. It is deliberately not a payment
provider, bank, tax engine, accounting system of record, or production charging
authority.

The engine uses integer currency minor units and integer pricing/usage micro
units. Price books, entitlements, usage, ledger transactions, invoices, credit
notes, webhook observations, audit events, and evidence reports are immutable.
Tenant isolation, idempotency, balanced double entry, maker/checker separation,
event-time rating, quote expiry/scope binding, and pre-side-effect budget checks
fail closed.

Local qualification can report at most `LOCAL_EXECUTED`; it never reports
external-gate readiness. The deterministic manifest maps all 18 exact Skill
names to concrete handler symbols and tests, and maps all 180 requirement IDs to
their owning handlers. Handler execution is `LOCAL_EXECUTED`, while every whole
Skill domain remains conservatively `PARTIAL`. Requirement states distinguish
bounded `LOCAL_EXECUTED` checks from `PARTIAL` behavior and `NOT_RUN` external
work.

All state is in-memory and same-process only. Restart durability, crash
recovery, payment sandbox/provider behavior, bank settlement, tax, accounting
system-of-record integration, disaster recovery, customer acceptance,
production execution, independent verification, and certification remain
`NOT_RUN` / `NOT_CERTIFIED`.

```bash
uv run --locked python -m elmos_pricing_billing.cli demo
uv run --locked python -m elmos_pricing_billing.cli scenario
uv run --locked python -m elmos_pricing_billing.cli qualify
uv run --locked python -m elmos_pricing_billing.cli manifest
uv run --locked pytest
uv run --locked ruff check .
uv run --locked mypy --strict src tests
```

No command performs a provider call, persists a credential, changes a real
subscription, sends an invoice, or charges money.
