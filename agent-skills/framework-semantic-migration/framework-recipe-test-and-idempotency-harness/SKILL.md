---
name: framework-recipe-test-and-idempotency-harness
description: "Test framework recipes with fixtures, native generation, startup, route, security, persistence, scheduling, source maps, and idempotency. Use before promoting or changing Batch 7 recipes."
---
# Framework Recipe Test and Idempotency Harness
Read `../references/afsm-v1.md`. Cover annotation fragments through real repository fixtures across framework/version/concern boundary cases. Require route-table tests for routes, denial tests for security, database rollback tests for transactions, database fixtures for ORM and fake clocks for scheduling.

Verify `Apply(Input) = Apply(Apply(Input))`, deterministic artifacts and source maps. Review golden changes and disable any recipe that lacks startup evidence, regresses behavior or fails idempotency.

