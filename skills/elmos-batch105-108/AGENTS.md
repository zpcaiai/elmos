# ELMOS Batch 105–108 implementation rules

1. A checked box is not evidence. Every DoD claim must point to an executed test, receipt or immutable artifact.
2. Never trust caller-provided `PASS`, `certified`, `destroyed`, `productionReady` or certificate level fields.
3. Tenant identity comes from authenticated server context, never a body/query tenant ID.
4. Every external side effect requires an idempotency key and durable receipt.
5. Preview runtime code is untrusted: per-run isolation, blocked cloud metadata, restricted egress, short-lived secrets and resource quotas are mandatory.
6. The 600-second preview TTL starts after READY, and public routing is revoked before compute destruction.
7. Do not delete tests, reduce coverage, skip checks, widen allowlists or suppress errors to make a migration green.
8. Keep deterministic rule changes, Agent changes and manual changes in separate provenance segments.
9. Generated packages and static validation never claim the target ELMOS product is implemented or production certified.
10. Run `./validate.sh` before publishing any modified package.
