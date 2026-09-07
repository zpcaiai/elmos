---
name: scheduler-background-job-and-worker-migrator
description: "Migrate cron, fixed-rate, fixed-delay, one-shot tasks, workers, durable jobs, and request-local background tasks. Use for framework scheduling or worker conversion."
---
# Scheduler Background Job and Worker Migrator
Read `../references/afsm-v1.md`. Classify task durability and execution model, then preserve cron dialect, timezone/DST, fixed-rate versus fixed-delay, misfire, retry, overlap, distributed lock/lease/fencing, idempotency and shutdown.

Never copy a cron string without conversion or use host timezone defaults. Block durable-job downgrade to an in-memory timer, missing multi-instance controls or unbounded retries. Generate fake-clock simulations.

