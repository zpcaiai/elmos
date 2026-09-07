---
name: platform-usage-metering-model
description: Define idempotent tenant/project/run meter events for repositories, compute, storage, models, builds, tests, migration data, egress, private capacity, and support. Use for quota and billing source-of-truth design.
---

# Platform Usage Metering Model

Read `../references/batch-12-enterprise-platform.md`. Record event ID, tenant/billing scope, meter, quantity/unit, resource, time and idempotency key from authenticated authorities. Use the same immutable facts for quota and billing; verify signed ordered offline imports.

Retry cannot double-meter and events contain no source. Duplicate or user-modifiable Meter facts block T-D.
