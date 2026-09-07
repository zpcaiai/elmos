---
name: virtual-clock-timezone-and-calendar-controller
description: "Control application clocks, timezones, calendars, TTLs, deadlines and scheduler time for Batch 9. Use for time-dependent source-target comparisons and boundary scenarios."
---

# Virtual Clock Timezone and Calendar Controller

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Select frozen, advancing or scripted virtual time.
2. Adapt source and target clock injection while keeping UTC, local, wall and monotonic semantics distinct.
3. Exercise month/year end, leap day, DST, expiry, cron, timeout, rollback and precision boundaries.

## Hard rules

- Do not rely on changing host time or real waiting.
- Do not delete business dates during normalization.
- Compare TTL and deadline behavior under the same semantic clock.

## Output

Emit a versioned timeline, adapter evidence and time-boundary results.

