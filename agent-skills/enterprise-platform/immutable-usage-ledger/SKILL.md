---
name: immutable-usage-ledger
description: Build an append-only, idempotent, ordered, hash-linked and recomputable usage Ledger with approved adjustment entries. Use for billing-period closure, offline import, disputes, or integrity verification.
---

# Immutable Usage Ledger

Read `../references/batch-12-enterprise-platform.md`. Derive entries from original Meter events, preserve source IDs and prior hashes, and represent corrections as reasoned approved positive/negative adjustments. Verify offline signatures and sequence before idempotent import.

Never update history. Hidden mutation, missing source event or unrecomputable totals blocks T-D.
