---
name: ef6-to-efcore-modernizer
description: Modernize EF6 applications in stages, supporting EF6 on modern .NET and per-context EF Core migration with schema, query, transaction, and data evidence.
---

# EF6 to EF Core Modernizer

Inventory every DbContext/ObjectContext, entity/model/mapping, provider, connection reference, migrations/history, EDMX, stored procedure, raw SQL, lazy/eager loading, proxies, conventions, interceptors, transactions, concurrency and database behavior.

## Staged workflow

1. Where supported, move the application to modern .NET while retaining EF6 and validate it.
2. Separate contexts and choose migration waves per context; EF6 and EF Core may coexist temporarily with explicit boundaries.
3. Port code-first contexts with provider/API behavior comparisons.
4. For EDMX Database First, do not convert the EDMX format. Scaffold a candidate EF Core code model from an approved test database/schema, preserve partial extensions, and review mappings.
5. Establish a new reviewed EF Core migration baseline. Never copy EF6 migration-history rows as if equivalent.
6. Compare schema, generated SQL, query results/order/null semantics, transactions, concurrency, stored procedures and performance.

## Required output

Produce EF inventory, per-context strategy/DAG, regenerated-model attribution, baseline decision, SQL/query/transaction/concurrency evidence and rollback steps. Missing test database/schema, unsupported provider behavior or unexplained query differences blocks promotion.
