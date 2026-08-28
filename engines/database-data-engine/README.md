# ELMOS Database and Data Platform Engine

This independently deployable Java 21 worker is ELMOS's fifth execution engine. Its repository-safe core declares vendor Runner boundaries, three independent modernization tracks, target-candidate policy, a governed migration state machine, canonical conversion obligations, cutover aggregation, and 24 deterministic accident scenarios.

Run the module with:

    JAVA_HOME=$(/usr/libexec/java_home -v 21) mvn -B -pl engines/database-data-engine -am verify
    java -jar engines/database-data-engine/target/elmos-database-data-engine-0.1.0-SNAPSHOT-exec.jar
    curl http://127.0.0.1:8089/engine/v1/capabilities

The worker exposes the shared capability, scan, plan, execute-step, validate, tenant-scoped job, and cancellation routes. Oracle, SQL Server, MySQL, PostgreSQL, Data Platform, and BI Validation Runners are declared but NOT_CONFIGURED. Requests that require database access or external evidence return terminal FAILED with empty evidence.

The static core never opens JDBC connections, launches host processes, loads vendor libraries, changes logging, starts CDC, writes customer data, or switches a production writer. Those actions require a short-lived job credential, a capability-matched approved Runner, explicit production authority, immutable provider evidence, and independent validation.

Five JSON Schema fixtures, the OpenAPI contract, and the 24 required Batch 15 incidents are checked by the module tests. These artifacts do not claim that a customer database, lakehouse, pipeline, report, or metric was migrated.

## Typed SQL transpilation

`sql-transpiler/` adds a pinned SQLGlot 30.13.0 typed-AST pipeline for PostgreSQL 17.5 and 18.4, MySQL 8.4.10 LTS, SQL Server 2022 CU26, Oracle 26ai, SQLite 3.53.3, and DuckDB 1.5.4. It exposes 42 directional syntax routes, exact profiles, a create-only CLI, target SQL and configuration generation, typed query IR, source/target AST evidence, fail-closed unsupported handling, and separated development/negative/holdout/representative corpora.

Run it independently:

```bash
cd engines/database-data-engine/sql-transpiler
uv sync --frozen
uv run pytest
uv run elmos-sql-transpiler transpile examples/postgresql-to-mysql.json /tmp/elmos-orders-mysql
uv run elmos-sql-transpiler verify-local-matrix /tmp/elmos-local-sql-matrix
```

The local syntax gate requires at least 99.5% success and currently passes its checked-in eligible corpus. The disposable runtime Runner additionally executes all six directed routes among exact PostgreSQL 17.5, SQLite 3.53.3, and DuckDB 1.5.4 profiles against the same deterministic data. It compares rows, logical types, cardinality, duplicates, order, errors, rollback/atomicity, lock conflicts, plans, and local p95 performance. Each execution emits content-addressed evidence. Profiles without an exact local runtime stay `BLOCKED` / `NOT_RUN`; independent holdout, production-like, security, and certification evidence remain `NOT_RUN` / `NOT_CERTIFIED`.

The transpiler also provides a repository-owned bounded runtime for all 47
exact ChinaDB commercial migration Skill identities. Every handler is callable
through the CLI and internal sidecar API, requires tenant/project/actor scope,
rejects inline secrets, and produces content-addressed local artifacts without
executing declared external effects. This is 100% local handler coverage, not
100% vendor route implementation: the immutable source package and all 78
commercial routes remain `SPEC_ONLY`; live vendor adapters, databases, CDC,
repository mutation, independent verification, and certification remain
`NOT_RUN` / `NOT_CERTIFIED`.

The repository also includes a production qualification intake for all 13
ChinaDB targets. It requires exact tuples, disposable environments, pinned
vendor tools, a digest-bound authorization, real execution evidence,
independent verification, and a separate Ed25519 certification decision. The
planner has no external side effects and returns no target SQL; the checked-in
draft therefore remains `productionDefinitionOfDoneCount = 0`. See
`docs/batch31/CHINADB_PRODUCTION_QUALIFICATION.md`.
