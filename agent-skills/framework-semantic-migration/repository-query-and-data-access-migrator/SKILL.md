---
name: repository-query-and-data-access-migrator
description: "Migrate repositories, ORM queries, query builders, raw SQL, stored procedures, projections, locking, pagination, and streaming. Use for AFSM query and repository lowering."
---
# Repository Query and Data Access Migrator
Read `../references/afsm-v1.md`. Preserve filter/join/null order/group/projection/distinct, stable pagination, tracking, locking, timeout, hints, batch, streaming and parameter binding.

Capture generated SQL and compare query shape and database results. Block unbounded client evaluation, unstable pagination, removed locks/timeouts, raw SQL concatenation, automatic stream materialization and unassessed N+1 changes.

