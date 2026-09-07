# ADR-0004 — PostgreSQL, Temporal, and object-storage ownership

## Status
Accepted.

## Context
Long tasks need durable orchestration, queryable business truth, and storage for large inputs/outputs. Making any one system own everything creates operational and query problems.

## Decision
PostgreSQL owns task/business/financial truth and transactional outbox. Temporal owns orchestration history, timers, signals, and retries. S3-compatible object storage owns large immutable content and logs.

## Consequences
- Contracts must bind IDs across systems.
- Workflow transitions are projected into PostgreSQL.
- Object availability/hash is verified before DB completion.
- Dual-write races are handled through outbox/update-with-start.
