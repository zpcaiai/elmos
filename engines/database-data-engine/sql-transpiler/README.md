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

## ChinaDB commercial extension boundary

The ChinaDB commercial registry adds 13 independent target identities and 78
planned routes (six source families by 13 targets): DM8, KingbaseES, openGauss,
TiDB, GBase 8s/8c/8a, HighGo/HGDB, OceanBase Oracle/MySQL modes, GaussDB
Oracle/M modes, and GoldenDB. PolarDB, PolarDB-X, and TDSQL are explicitly
excluded.

The imported package and its 78 route declarations remain immutable
`SPEC_ONLY` source material. Separately, the repository now binds all 47 exact
Skill IDs to bounded local code handlers. Those handlers implement typed local
inventory, IR, rule, movement-plan, conversion-assessment, procedural,
application-refactor, verifier, repair, cutover, evidence, release, six source,
five application, 13 target-contract, route-matrix, mutation, benchmark,
estimation, vendor-bridge, and observability operations. They require exact
tenant/project/actor scope, reject inline secrets and ambiguous JSON, produce
content-addressed results, and execute no provider/database/repository effect.

`47/47 CODE_IMPLEMENTED` therefore means every exact Skill has executable
repository-owned bounded handler code and tests. It does not mean the source
package was mutated to claim implementation, or that 13 vendor renderers and
databases were independently exercised. Exact target SQL emission, target
apply/introspection, source/target execution, vendor tools, production cutover,
independent verification, and certification remain `NOT_RUN` /
`NOT_CERTIFIED`.

`commercial-assess` is a read-only preflight. It requires an existing exact
source profile, concrete target ID/version/edition/compatibility mode/driver/
charset/collation/time zone, and a SHA-256 capability-snapshot identity. It
parses source SQL into typed AST and semantic
obligations, but it always returns `BLOCKED`, includes explicit blockers, and
sets `targetSql` to null because no commercial target renderer or target
capability snapshot has been independently verified. The example snapshot
digest is a specimen identity only and is deliberately reported as unverified.

The machine-readable contracts are:

- `schemas/batch31/chinadb-commercial-capabilities.schema.json`
- `schemas/batch31/chinadb-sql-preflight-request.schema.json`
- `schemas/batch31/chinadb-sql-preflight-result.schema.json`
- `schemas/batch31/chinadb-skill-capabilities.schema.json`
- `schemas/batch31/chinadb-skill-request.schema.json`
- `schemas/batch31/chinadb-skill-result.schema.json`
- `schemas/batch31/chinadb-production-qualification-requirements.schema.json`
- `schemas/batch31/chinadb-production-qualification-request.schema.json`
- `schemas/batch31/chinadb-production-trust-store.schema.json`
- `schemas/batch31/chinadb-production-qualification-result.schema.json`

## Run

```bash
uv sync --frozen
uv run pytest
uv run elmos-sql-transpiler capabilities
uv run elmos-sql-transpiler commercial-capabilities
uv run elmos-sql-transpiler commercial-capabilities \
  --output /tmp/elmos-chinadb-commercial-capabilities.json
uv run elmos-sql-transpiler commercial-assess \
  examples/chinadb-commercial-assess.json \
  --output /tmp/elmos-chinadb-commercial-assessment.json
uv run elmos-sql-transpiler commercial-skill-capabilities \
  --output /tmp/elmos-chinadb-skill-capabilities.json
uv run elmos-sql-transpiler commercial-skill-run \
  01-estate-inventory-assessment \
  examples/chinadb-skill-inventory.json \
  --output /tmp/elmos-chinadb-inventory-result.json
uv run elmos-sql-transpiler commercial-production-requirements \
  --output /tmp/elmos-chinadb-production-requirements.json
uv run elmos-sql-transpiler commercial-production-template \
  --tenant-id tenant-required \
  --project-id project-required \
  --actor-id actor-required \
  --implementer-organization-id organization-required \
  --output /tmp/elmos-chinadb-production-request.json
uv run elmos-sql-transpiler commercial-production-plan \
  /tmp/elmos-chinadb-production-request.json \
  --output /tmp/elmos-chinadb-production-plan.json
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

Capability and assessment `--output` files are create-only. The commercial
assessment command returns exit status 3 after successfully writing its typed
`BLOCKED` result; exit status 0 would incorrectly suggest a renderer is ready.
Skill capability and execution outputs are also create-only. A bounded handler
returns exit status 0 for local completion/human/external-gate readiness and 3
for an explicit local or external block; neither status is certification.

The sidecar exposes the same local surface at:

- `GET /internal/v1/chinadb-skills/capabilities`
- `POST /internal/v1/chinadb-skills/{skill_id}/execute`
- `GET /internal/v1/chinadb-production/requirements`
- `POST /internal/v1/chinadb-production/plan`

The execution endpoint accepts strict UTF-8 JSON with no duplicate fields,
requires exact `scope.tenantId`, `scope.projectId`, and `scope.actorId`, is
request/response/concurrency bounded, and rejects inline credential material.

The production qualification planner validates the 13 exact target tuples,
disposable environments, vendor tool versions/digests, authorizations, and
independent-verifier separation. Production completion requires a
digest-chained Ed25519 authorization, execution, independent-verification, and
certification receipt from an operator-pinned trust store. Planning performs
no external call and returns no target SQL; without those real receipts the
five production boundary fields remain `NOT_RUN` / `NOT_CERTIFIED` / `null` /
`0`. See `docs/batch31/CHINADB_PRODUCTION_QUALIFICATION.md`.

The output directory is create-only. A successful materialization contains target SQL, typed source/target AST, source and target profiles, route, source map identity, Runner configuration, verification state, and a transpilation report. The raw source SQL is not copied, although its typed AST and literals are retained in the canonical IR; customer handling policy still applies.

## Meaning of success

`SYNTAX_READY` means:

1. the installed parser is the exact build the profile catalog pins
   (a different `sqlglot` raises `EXACT_PARSER_MISMATCH` rather than
   translating with an unverified frontend);
2. the exact source dialect parsed without recovery;
3. no opaque command node was accepted;
4. typed canonical normalization completed;
5. every bind parameter was rewritten into the target dialect's own
   placeholder syntax, one source parameter to one target parameter;
6. the target emitter reported no unsupported semantics;
7. the generated target SQL reparsed in the exact target dialect;
8. parameter-node cardinality was preserved and every emitted placeholder is
   a real placeholder in the target engine.

It does not mean the target database executed the SQL or returned equivalent rows, types, ordering, errors, locks, plans, or performance. Those remain `NOT_RUN`; certification remains `NOT_CERTIFIED`.

### Target adapter protocol and trace

All existing exact-profile emission now passes through the versioned target
adapter protocol and registry. Each adapter is bound to one exact profile and
dialect; the registry refuses duplicate or absent adapters. Successful
transpilation metadata records the adapter ID, protocol and implementation
versions, adapter digest, per-rule input/output/rule digests, and a digest of
the ordered rule trace. This makes core SQLGlot emission auditable without
turning ChinaDB compatibility labels into core dialect aliases.

### Bind parameters

`sqlglot` does not translate placeholders between dialects: it renders each
parameter node with whatever syntax the *target generator* uses for that node
type. For every cross-engine pair here that is not a placeholder at all --
PostgreSQL `$1` becomes MySQL `@1` (a session variable), Oracle `:one` becomes
PostgreSQL `%(one)s` (psycopg client syntax), SQL Server `@p1` becomes
PostgreSQL `$p1` (invalid). None of those are syntax errors, so the re-parse
leg cannot catch them; a query translated that way binds nothing and matches
the wrong rows. `placeholders.py` owns this: it rewrites each parameter into
the target's real syntax (`$n` / `?` / `@name` / `:name`), keeps one source
parameter mapped to one target parameter, refuses a repeated parameter when
the target's placeholders are positional and anonymous, and verifies every
emitted token against the target's placeholder grammar.

### Divergences that are legal SQL on both sides

Two differences cannot be fixed by translation, because the statement is valid
in both dialects and simply computes something different. They are reported as
`WARNING` diagnostics, with the matching semantic obligation on the statement:

* `INTEGER_DIVISION_SEMANTICS_DIFFER` -- `/` on two integers truncates in
  PostgreSQL, SQL Server and SQLite (`7 / 2` is 3) and returns a fractional
  result in MySQL, Oracle and DuckDB (`3.5`); division by zero raises in the
  first group and yields NULL in MySQL. Which behaviour applies depends on the
  column types, which this profile has no catalog for.
* `IDENTIFIER_CASE_FOLDING_DIFFERS` -- PostgreSQL and DuckDB fold unquoted
  identifiers to lower case, Oracle to upper case, MySQL/SQLite/SQL Server
  preserve them, so `SELECT Foo FROM Bar` names different objects on the two
  sides of such a route.

A positional `GROUP BY` / `ORDER BY` against a wildcard projection
(`SELECT * FROM t ORDER BY 1`) is refused outright: resolving position 1
requires the table's column list, and substituting the projection node emits
`ORDER BY *`, which sqlglot re-parses and every real server rejects.

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
