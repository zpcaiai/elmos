# ChinaDB commercial SQL extension

This Batch 31 extension exposes a fail-closed SQL conversion preflight for the
`chinadb-commercial-migration-skills` v1.0.0 planning package. It registers the
package's 13 target families and 78 planned directed routes without claiming
that a target adapter, renderer, database execution, equivalence run, or
certification exists.

## Contracts

- `schemas/batch31/chinadb-commercial-capabilities.schema.json` fixes the
  inventory boundary at 13 targets and 78 planned routes. All capability and
  route states remain `SPEC_ONLY`, external execution remains `NOT_RUN`, and
  certification remains `NOT_CERTIFIED`.
- `schemas/batch31/chinadb-sql-preflight-request.schema.json` accepts only the
  seven exact source profiles already registered by the Batch 31 SQL intake.
  The target id, exact target version, edition, compatibility mode, driver,
  charset, collation, time zone, and capability snapshot digest are mandatory
  route inputs.
- `schemas/batch31/chinadb-sql-preflight-result.schema.json` permits a typed
  source AST and semantic obligations after a successful source parse, or an
  empty statement list plus explicit blocker after a failed parse. It fixes the
  result to `BLOCKED` while the commercial target adapters are specifications
  only. `targetSql` is required and must be explicitly `null`; omission or any
  emitted target SQL is invalid.
  All target/runtime/external verification fields remain `NOT_RUN` and
  certification remains `NOT_CERTIFIED`.

The DB2 LUW and Sybase ASE families remain in the 78-route planning inventory,
but no exact DB2 or Sybase intake profile is fabricated. SQLite and DuckDB keep
their existing exact parser profiles, but they are not part of the 78
commercial routes and therefore receive an explicit route-not-planned blocker.

PolarDB, PolarDB-X, and TDSQL remain excluded by the source package contract.

## Runtime topology and authorization

The implemented path is deliberately one-way and bounded:

```text
Web BFF -> authenticated control-plane -> database-data worker
        -> isolated Python typed-preflight sidecar -> SQLGlot source parser
```

- `GET /api/capabilities/database-sql` requires `workspace:view` and proxies the
  immutable capability digest through the control-plane and worker.
- `POST /api/database-sql/preflight` requires `translation:execute`. The BFF
  does not accept tenant or actor identifiers from the browser; the
  control-plane derives both from the authenticated principal and the worker
  supplies them only as internal headers to the sidecar hop.
- The Python service runs the parser assessment in a spawned child process,
  with one concurrent assessment, a 15-second deadline, a 1,310,720-byte JSON
  envelope, 256-KiB UTF-8 SQL, 256 parameters, 256 statements, and a 4-MiB
  response limit. Duplicate JSON fields, non-UTF-8 text, encoded/chunked bodies,
  stale capability digests, response drift, and ambiguous upstream status all
  fail closed.
- The sidecar has no database credentials or customer workspace mount. Its
  Compose network is internal and reachable only by the database-data worker.
  Production services are behind the opt-in `chinadb-sql` profile and the Web,
  control-plane, and worker feature flags remain disabled unless explicitly
  configured together.

The implementation performs typed **source** parsing and obligation analysis
only. It does not bind any commercial target adapter or vendor renderer. Every
successful HTTP assessment therefore still returns `state: BLOCKED`, a
required `targetSql: null`, target/runtime/external checks as `NOT_RUN`, and
`certification: NOT_CERTIFIED`.

## Local engineering checks

The bounded local implementation can be checked without connecting to any
target database:

```sh
cd engines/database-data-engine/sql-transpiler
uv run --frozen pytest
uv run --frozen ruff check src tests
uv run --frozen mypy

cd ../../..
mvn -pl engines/database-data-engine -am \
  -Dtest=ChinaDbSqlPreflightProtocolTest,DatabaseDataEngineControllerTest,Batch15ContractFixtureTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
mvn -pl apps/control-plane -am -Dtest=DatabaseDataControllerTest \
  -Dsurefire.failIfNoSpecifiedTests=false test
pnpm --dir apps/web-console test:chinadb-sql-policy
```

These commands are local engineering evidence. They do not execute DM8,
KingbaseES, openGauss, TiDB, GBase, HighGo, OceanBase, GaussDB, GoldenDB, or an
independent holdout/certification environment.

## Schema tests

Run the independent positive and negative contract tests with:

```sh
uv run --with jsonschema python -m unittest discover \
  -s tests/chinadb-sql-extension-schema -p 'test_*.py' -v
```

Schema validation proves only contract shape and fail-closed state handling. It
does not provide target runtime, differential, holdout, production, or
certification evidence.
