# Batch 31 typed SQL transpilation

## Outcome

ELMOS provides a project-usable, typed SQL transpilation pipeline for seven exact profiles and 42 directional routes:

| Profile | Grammar backend | Checked-in state | Runtime evidence |
|---|---|---|---|
| PostgreSQL 17.5 Community | `postgres` | local Runner ready | generated per execution |
| PostgreSQL 18.4 Community | `postgres` | syntax experimental | `NOT_RUN` |
| MySQL 8.4.10 LTS Community | `mysql` | syntax experimental | `NOT_RUN` |
| SQL Server 2022 Enterprise CU26 | `tsql` | licensed runtime required | `NOT_RUN` |
| Oracle AI Database 26ai Enterprise | `oracle` | licensed runtime required | `NOT_RUN` |
| SQLite 3.53.3 | `sqlite` | syntax experimental | `NOT_RUN` |
| DuckDB 1.5.4 | `duckdb` | local Runner ready | generated per execution |

The parser/emitter dependency is pinned to SQLGlot 30.13.0. The implementation never uses regular-expression replacement as the transformation core.

## Near-100-percent contract

The local syntax objective is at least `99.5%` over the declared eligible capability set. A case counts as successful only when:

- source parsing uses the selected exact dialect and raises on parse errors;
- the source becomes a typed AST rather than an opaque command;
- canonical typed transformations complete;
- target emission raises on unsupported semantics;
- emitted SQL reparses under the exact target dialect;
- parameters are not silently dropped;
- no silent fallback or permissive raw-command output is used.

The checked-in synthetic qualification suite currently covers all 42 routes, requires development, holdout, and representative cases on each route, requires at least five positive cases per route, and separately tests negative and known-unsupported behavior. Its local result is 248/248 eligible syntax cases and 44/44 fail-closed negative cases.

This is local engineering evidence, not a universal SQL guarantee. The upstream parser itself explicitly does not claim it can parse every possible statement. Stored procedures, triggers, optimizer hints, vendor-specific transaction behavior, schema/type equivalence, and unmodeled extensions remain blocked or conditional.

For a Batch 31 route to become certified:

- all P0 source and target queries must execute on exact real engines;
- row values, types, cardinality, duplicates, explicit ordering, nulls, and errors must be 100% equivalent;
- critical precision, collation, transaction, security, and data regressions must be zero;
- development, negative, independent holdout, and representative workloads must all pass;
- performance, rollback, source mapping, evidence digests, and independent verification must pass the Batch 31 gate.

Thus `99.5%` is a syntax coverage goal. P0 semantic correctness remains `100%` or the route fails closed.

## Generated project artifacts

Each successful conversion creates:

```text
target.sql
canonical-ir/query-ir.json
route.json
source-reference.json
target-profile.json
runner-config.json
verification.json
transpilation-report.json
```

`runner-config.json` grants only read access to the source and disposable-schema access to the target. Production writes are prohibited without separate approval. Generated verification states start with source execution, target execution, result/error equivalence, performance, security, and certification as `NOT_RUN` or `NOT_CERTIFIED`.

## Commands

```bash
cd engines/database-data-engine/sql-transpiler
uv sync --frozen
uv run pytest

uv run elmos-sql-transpiler transpile \
  examples/postgresql-to-mysql.json \
  /tmp/elmos-orders-mysql

uv run elmos-sql-transpiler qualify \
  corpus/development/queries.json \
  corpus/negative/queries.json \
  corpus/holdout/queries.json \
  corpus/representative/queries.json
```

The request and result contracts are:

- `schemas/batch31/sql-transpilation-request.schema.json`
- `schemas/batch31/sql-transpilation-result.schema.json`

## Next exact profiles

- MariaDB requires a native semantic adapter; it is not certified through a MySQL alias.
- IBM Db2 requires an exact grammar/emitter and licensed execution profile.
- BigQuery, Snowflake, ClickHouse, Redshift, and Databricks SQL require separate provider/version/service-tier profiles and representative analytical workloads.
- PL/SQL, T-SQL, PL/pgSQL, MySQL routines, and triggers use the Batch 31 routine migration pipeline rather than the query-only syntax path.
