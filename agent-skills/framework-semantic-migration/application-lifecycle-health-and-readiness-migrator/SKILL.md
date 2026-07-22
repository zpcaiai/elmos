---
name: application-lifecycle-health-and-readiness-migrator
description: "Migrate startup, warmup, readiness, draining, shutdown, cleanup, liveness, and dependency health contracts. Use for framework host and resource lifecycle conversion."
---
# Application Lifecycle Health and Readiness Migrator
Read `../references/afsm-v1.md`. Preserve configuration/dependency/startup/warmup/ready/running/draining/shutdown/disposed phases, ordering, timeouts, failure and resource cleanup.

Do not report readiness before required resources are ready or make liveness depend on transient outages. Disable destructive health actions and secret output. Require graceful drain/shutdown tests for HTTP, consumers, schedulers, pools and runtime resources.

