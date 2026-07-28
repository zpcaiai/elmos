# ELMOS typed SQL transpiler

This module is the local, fail-closed SQL syntax transpilation component of the ELMOS database and data-platform engine. It uses SQLGlot 30.13.0 as a pinned multi-dialect parser and emitter, but wraps it with exact engine profiles, typed AST evidence, target reparsing, parameter checks, route coverage, separated corpora, explicit semantic obligations, and Batch 31 evidence boundaries.

## Exact core profiles

- PostgreSQL 17.5 Community with a local native Runner
- PostgreSQL 18.4 Community
- MySQL 8.4.10 LTS Community
- SQL Server 2022 Enterprise CU26, build 16.0.4265.3
- Oracle AI Database 26ai Enterprise
- SQLite 3.53.3
- DuckDB 1.5.4

These seven profiles form 42 directional syntax routes. Reverse directions are distinct. The local execution Runner is limited to PostgreSQL 17.5, SQLite 3.53.3, and DuckDB 1.5.4. MariaDB, DB2, BigQuery, Snowflake, and ClickHouse are registered as conditional, detected-only, or planned instead of being silently aliased to another engine.

## Run

```bash
uv sync --frozen
uv run pytest
uv run elmos-sql-transpiler capabilities
uv run elmos-sql-transpiler transpile \
  examples/postgresql-to-mysql.json \
  /tmp/elmos-orders-mysql
uv run elmos-sql-transpiler qualify \
  corpus/development/queries.json \
  corpus/negative/queries.json \
  corpus/holdout/queries.json \
  corpus/representative/queries.json
```

The output directory is create-only. A successful materialization contains target SQL, typed source/target AST, source and target profiles, route, source map identity, Runner configuration, verification state, and a transpilation report. The raw source SQL is not copied, although its typed AST and literals are retained in the canonical IR; customer handling policy still applies.

## Meaning of success

`SYNTAX_READY` means:

1. the exact source dialect parsed without recovery;
2. no opaque command node was accepted;
3. typed canonical normalization completed;
4. the target emitter reported no unsupported semantics;
5. the generated target SQL reparsed in the exact target dialect;
6. parameter-node cardinality was preserved.

It does not mean the target database executed the SQL or returned equivalent rows, types, ordering, errors, locks, plans, or performance. Those remain `NOT_RUN`; certification remains `NOT_CERTIFIED`.
