---
name: database-transaction-cache-scanner
description: Identify database, ORM, transaction and cache migration risks in Java legacy systems. Use for JPA/Hibernate, native SQL, transactional proxy, schema, Redis or Spring Cache analysis.
---
# Database Transaction Cache Scanner

## Workflow
1. Inventory persistence APIs, dialects, native queries, migrations and transaction annotations.
2. Flag legacy javax persistence, private transactional methods and dynamic native SQL.
3. Record cache annotations, providers, invalidation and TTL evidence separately.
4. Require runtime/schema tests for behavioral claims.

## Acceptance
- Static findings never claim transaction equivalence.
- Missing schema, TTL or integration evidence is `INCONCLUSIVE`.
- High-risk findings create Batch 4 data-review gates.

