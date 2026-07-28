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

uv run elmos-sql-transpiler runner-capabilities
uv run elmos-sql-transpiler verify-route \
  postgresql-17.5 \
  duckdb-1.5.4 \
  /tmp/elmos-postgresql-to-duckdb
uv run elmos-sql-transpiler verify-local-matrix \
  /tmp/elmos-local-sql-matrix
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

## Exact local runtime Runner

The runtime command uses only three exact tuples available on the declared
`darwin-arm64` host:

- PostgreSQL server 17.5 from the pinned Homebrew keg with
  `psycopg-binary` 3.3.4;
- SQLite 3.53.3 embedded in Python 3.14.6;
- DuckDB 1.5.4 with `duckdb-python` 1.5.4.

PostgreSQL is provisioned with a fresh temporary `initdb` cluster and a
loopback-only ephemeral port. SQLite and DuckDB use temporary database files.
All three receive the same 2,000 deterministic synthetic orders, and every
temporary database is destroyed after execution. No customer or production
database is accepted by this Runner.

Each directed route executes six query contracts covering row values, logical
types, cardinality, explicit order, duplicates, nulls, timestamps, aggregation,
windows and pagination. It also verifies duplicate-key errors, explicit
rollback, statement-failure atomicity, a bounded two-connection write-conflict
schedule, real query plans, and warmed p50/p95 timings against a declared local
75 ms p95 SLO.

Each route output is create-only and contains:

```text
fixture.json
query-results.json
error-equivalence.json
transaction-locking.json
performance.json
plans/source-plan.json
plans/target-plan.json
environment.json
gate-result.json
gate-report.md
runner-evidence.json
```

`runner-evidence.json` binds every other evidence file by SHA-256 digest and
byte count. A local pass means `READY_FOR_EXTERNAL_GATE`, not certification.
Independent holdout execution, representative production-like execution and
independent verification remain `NOT_RUN`; certification remains
`NOT_CERTIFIED`.
