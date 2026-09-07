# Financial and Execution Invariants

These assertions should exist as unit/property tests, database constraints where possible, runtime monitors, and reconciliation checks.

## Ledger

1. Every posted transaction has at least two entries.
2. Debit total equals credit total for exactly one unit/currency per transaction.
3. Posted transactions and entries are immutable.
4. Reversal references the original transaction and does not delete it.
5. Balance projection can be rebuilt exactly from the ledger cursor.

## Wallet and authorization

6. Non-credit accounts never have unauthorized negative available balance.
7. `captured + released <= authorized` for every authorization.
8. The same idempotency key and operation returns the same result.
9. A released/expired authorization is not captured without new authority.
10. Paid and promotional credit provenance remains distinguishable.

## Usage and rating

11. One source event produces at most one normalized usage fact.
12. Corrections preserve the original event.
13. Event-time vendor and customer rate versions are retained.
14. Aggregates reconcile to details.
15. BYOK excludes only policy-defined customer-owned model cost.

## Quote and project

16. A task cannot enter RUNNING without an accepted, unexpired quote and active authorization.
17. Customer capture cannot exceed accepted hard cap plus explicit top-ups.
18. Machine wall-clock ETA is separate from human effort.
19. Fixed/capped project scope and source baseline are immutable without a change order.
20. Project completion requires acceptance evidence, not just generated files.

## Invoice, payment, refund

21. Finalized invoices are immutable.
22. Payment browser redirect never creates financial truth by itself.
23. One provider event/charge creates at most one business effect.
24. Cumulative refunds do not exceed the refundable basis.
25. Provider, invoice, payment and ledger differences enter suspense, not silent repair.

## Security and operations

26. Tenant isolation is enforced at a trusted layer for every customer fact.
27. No secret appears in logs, prompts, usage events or analytics.
28. Maker cannot approve their own high-risk adjustment.
29. Replay and recovery preserve all financial invariants.
30. Critical invariant failure stops affected new financial writes.
