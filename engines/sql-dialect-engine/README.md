# ELMOS SQL Dialect Engine

This engine translates DDL and a conservative SQL routine subset between four exact database dialects -- PostgreSQL,
MySQL, Oracle, and SQL Server (T-SQL) -- under a fixed, precisely bounded
profiles `certified-ddl-v1`, `certified-alter-v1`, `certified-drop-v1`,
`certified-schema-v1`, `certified-insert-v1`, `certified-routine-v1`, `certified-view-v1`,
`certified-comment-v1`, `certified-privilege-v1`, `certified-dml-v1`, and
`certified-rls-v1`.
Every directed pair among the four
dialects is independent, giving 12 supported translation routes.

The scanner also includes the 13 exact ChinaDB commercial target identities:
DM8, KingbaseES, openGauss, TiDB, GBase 8s/8c/8a, HighGo/HGDB, OceanBase
Oracle/MySQL modes, GaussDB Oracle/M modes, and GoldenDB. They are represented
as `SPEC_ONLY` provider targets with 78 planned source-family routes. A
compatibility label is not treated as a verified dialect alias, so no target
SQL is emitted for these targets until an exact versioned adapter, target
parser, and independent evidence are present.

## What the 100% measurement means here

Arbitrary SQL cannot be translated across dialects with a guaranteed success
rate: dialects diverge in stored procedures, window function edge cases,
locking hints, partitioning, vendor-specific functions, and dozens of other
constructs that have no common semantic ground. Any tool that claims 100% on
*arbitrary* SQL is either lying or silently producing wrong output on the
cases it can't actually handle -- exactly the failure mode this repository's
other engines (see `engines/polyglot-route-engine`, `CanonicalDatabaseIr`'s
`DynamicSqlStatus`) already refuse to accept.

So this engine draws a hard line instead: the scanner gives every discovered
SQL unit an explicit disposition. The current measured result is
**1485/1485 = 100.0% disposition coverage**: each unit is either an automatic
translation candidate, a manual migration requirement, source-format review,
or an engine defect. This is the 100% completeness measure; it does not
relabel manual work as translated.

The separate automatic-translation measure remains an upper bound. On the
current 76-file migration corpus it is **1173/1485 = 79.0%**, after adding
typed namespace mapping, views, callable and constraint comments, table
privileges, bounded procedures, table-valued functions, literal-only INSERT
seeds, bounded single-source `INSERT ... SELECT`, simple single-table `UPDATE`,
PostgreSQL adjacent-string recovery, trigger metadata, JSON/plain binary
routes, typed TRIM/BTRIM and null-test CHECK equality, same-typed numeric CHECK addition,
bounded INNER JOIN INSERT ... SELECT, and the existing DDL/ALTER/routine expansions. The remaining statements include
security-sensitive procedural blocks, dynamic SQL, RLS, JSONB/arrays, and
vendor-specific constructs with no proven common semantics. The engine raises
`DialectError` and reports `status: "BLOCKED"` for those cases rather than
guessing. External execution, independent verification, and certification
remain separate evidence gates.

For the domestic target ledger, the current scan expands every discovered
source unit against all 13 ChinaDB targets: **19305/19305 = 100.0% route
disposition coverage**. An admitted source unit receives
`TARGET_ADAPTER_REVIEW_REQUIRED`; an already blocked source unit retains its
manual or source-format disposition. This is complete, auditable route
accounting, not 100% automatic ChinaDB conversion: automatic target emissions
remain `0`, external execution remains `NOT_RUN`, and certification remains
`NOT_CERTIFIED`.

The source-side number is not the same as target reachability. Replaying every
source-side candidate through all four target emitters gives **343/1173 = 29.2%**
with no target namespace profile, with per-target reachability of PostgreSQL
1173, MySQL 411, Oracle 404, and SQL Server 413. When the caller explicitly
declares the source default namespace mapping `{"": "dbo"}`, SQL Server table
and column comments can use extended properties, raising the profile-specific
intersection to **393/1173 = 33.5%** (SQL Server 468; MySQL column comments use
the complete source column definition when a comment catalogue is supplied).
These are emitter
reachability upper bounds, not live-database execution or certification.

## Certified SQL profile scope

One statement per call: a single `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE`,
portable `DROP TABLE`, minimal `CREATE SCHEMA`, fixed-column literal
`INSERT ... VALUES`, bounded single-source `INSERT ... SELECT`, single-table
`UPDATE`, routine, ordinary `CREATE VIEW`, table `GRANT`/`REVOKE`, or
`COMMENT ON TABLE/COLUMN/FUNCTION/CONSTRAINT`. Qualified names are
accepted only with an explicit `--namespace-map` source-to-target mapping;
an empty source key maps unqualified objects to the target default schema.
quoted/escaped identifiers remain outside the certified plain-identifier
contract (`[A-Za-z_][A-Za-z0-9_]*`). RLS policies are intentionally exposed as
`certified-rls-v1` blockers until a target policy model exists. Unsupported
units remain visible in the scanner's 100% disposition ledger.

**Column types** (canonical, with dialect-specific spelling on each side):
`BOOLEAN`, `INT16`/`INT32`/`INT64`, `DECIMAL(p,s)`, `CHAR(n)`, `VARCHAR(n)`,
`TEXT` (including SQL Server's `VARCHAR(MAX)`/`NVARCHAR(MAX)` and MySQL's
`TINYTEXT`/`TEXT`/`MEDIUMTEXT`/`LONGTEXT`, which all round-trip to `TEXT`
canonically), `DATE`, `TIMESTAMP`, plain `JSON`, and explicitly bounded
`BINARY`. PostgreSQL `JSONB` retains its binary semantic bit and is rejected
when the target cannot preserve it; arrays retain their typed element but are
rejected without an exact target collection route. MySQL's `TIMESTAMP`, SQL Server's
`DATETIME`/`DATETIME2`, and timezone-aware timestamp forms all collapse to
one canonical `TIMESTAMP` -- this profile does not model timezone-awareness
or precision distinctions separately. SQL Server's `BIT` and Oracle's
`NUMBER(1)`-as-boolean idiom both map to canonical `BOOLEAN`.

The rendered type per target is chosen so a translation is always a widening
or an exact match, never a silent narrowing. The non-obvious ones, each
locked down by `tests/test_type_mapping_fidelity.py`:

| Canonical | postgres | mysql | oracle | tsql |
| --- | --- | --- | --- | --- |
| `VARCHAR(n)` | `VARCHAR(n)` | `VARCHAR(n)` | `VARCHAR2(n CHAR)` | `NVARCHAR(n)` |
| `CHAR(n)` | `CHAR(n)` | `CHAR(n)` | `CHAR(n CHAR)` | `NCHAR(n)` |
| `TEXT` | `TEXT` | `LONGTEXT` | `CLOB` | `NVARCHAR(MAX)` |
| `TIMESTAMP` | `TIMESTAMP` | `DATETIME` | `TIMESTAMP` | `DATETIME2` |
| `DEFAULT CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` | `SYSDATETIME()` |

* **Oracle `n CHAR`** -- Oracle's default length semantics is `BYTE`, so a
  bare `VARCHAR2(50)` holds 50 *bytes*, as few as 12 characters in AL32UTF8.
  Every other dialect here counts characters.
* **SQL Server `N` types** -- `CHAR`/`VARCHAR`/`TEXT` on SQL Server are
  single-byte code-page types; a UTF-8 source column routed into them loses
  every character the server collation cannot represent.
* **MySQL `DATETIME`, not `TIMESTAMP`** -- MySQL's `TIMESTAMP` is stored as
  UTC and converted per session, is limited to 1970..2038, and (with the
  default `explicit_defaults_for_timestamp=OFF`) silently gains
  `NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`.
* **MySQL `LONGTEXT`, not `TEXT`** -- MySQL's `TEXT` caps at 65,535 bytes.
* **SQL Server `SYSDATETIME()`, not `GETDATE()`** -- `GETDATE()` returns the
  legacy `datetime` type (3.33 ms granularity, range 1753-9999) and would
  truncate the `DATETIME2` column this profile renders.

Vendor integer spellings widen to the smallest canonical integer that holds
their whole documented range, so a real `SHOW CREATE TABLE` / mysqldump reads
cleanly and nothing is ever narrowed: `TINYINT` and `TINYINT UNSIGNED` to
`INT16`, `SMALLINT UNSIGNED`/`MEDIUMINT`/`MEDIUMINT UNSIGNED` to `INT32`,
`INT UNSIGNED` to `INT64`. MySQL's `TINYINT(1)` reads as canonical `BOOLEAN`,
because that *is* MySQL's boolean storage -- `BOOLEAN` is an alias for it and
the server echoes `tinyint(1)` back. A `TINYINT(1)` used as a small integer
instead is outside that reading; declare it `TINYINT(4)` or `SMALLINT`.

Oracle has no native fixed-width integer, so `INT16`/`INT32`/`INT64` render as
`NUMBER(5)`/`NUMBER(10)`/`NUMBER(19)`, and an Oracle `NUMBER(p)` reads back as
`DECIMAL(p, 0)` rather than an integer. That asymmetry is deliberate:
`NUMBER(10)` holds 9,999,999,999, which `INT32` does not, so the reverse
mapping would narrow a real column. Both directions are pinned by tests.

Three source spellings that *look* translatable are rejected instead, because
every fixed substitute silently loses data:

* `BIGINT UNSIGNED` -- reaches 18,446,744,073,709,551,615, which no canonical
  integer holds and which PostgreSQL, Oracle and SQL Server cannot express at
  all (`CERTIFIED_DDL_UNSIGNED_BIGINT_UNREPRESENTABLE`). `DECIMAL(20, 0)` is
  the exact substitute, but it is a different type class, so this profile asks
  rather than decides.

* `VARCHAR` with no length -- unlimited in PostgreSQL (read as canonical
  `TEXT`), but `VARCHAR(1)` in SQL Server and rejected outright by MySQL and
  Oracle, so it is only accepted from a PostgreSQL source
  (`CERTIFIED_DDL_UNBOUNDED_VARCHAR`).
* `DECIMAL`/`NUMBER` with no precision -- arbitrary precision in PostgreSQL
  and Oracle, with no fixed-precision equivalent anywhere else
  (`CERTIFIED_DDL_UNBOUNDED_DECIMAL`).

Lengths and precisions beyond a target vendor's documented maximum (Oracle
`VARCHAR2` 4000, SQL Server `NVARCHAR` 4000, MySQL `CHAR` 255, Oracle/SQL
Server `DECIMAL` precision 38, MySQL scale 30, ...) are reported as
`CERTIFIED_DDL_LENGTH_EXCEEDS_TARGET` / `CERTIFIED_DDL_PRECISION_EXCEEDS_TARGET`
rather than emitted as DDL the target server would reject.

**Column features:** `NOT NULL`, a literal or `CURRENT_TIMESTAMP` `DEFAULT`,
inline `PRIMARY KEY`, inline `UNIQUE`, and auto-increment/identity columns
(MySQL `AUTO_INCREMENT`, Postgres/Oracle `GENERATED BY DEFAULT AS IDENTITY`,
SQL Server `IDENTITY(1,1)`) -- each dialect's own correct spelling is
emitted, never another dialect's keyword passed through verbatim (see "Why
not just use sqlglot's own generator" below). One rule the syntax leg cannot
see: **MySQL requires an AUTO_INCREMENT column to be a key** (errno 1075),
while the other three accept a non-key identity column, so translating one
into MySQL is reported as `CERTIFIED_DDL_MYSQL_AUTO_INCREMENT_NOT_KEY` rather
than emitted as DDL the server rejects.

**Table-level constraints:** `PRIMARY KEY (...)`, `UNIQUE (...)`,
`FOREIGN KEY (...) REFERENCES table (...)` with `ON DELETE`/`ON UPDATE` of
`CASCADE`/`SET NULL`/`RESTRICT`/`NO ACTION`, and `CHECK (...)` -- named or
unnamed, both AST shapes are handled. CHECK supports a typed boolean tree of
`AND`/`OR`/`NOT`, null tests, boolean assertions, column-to-column comparisons,
literal comparisons, `IN`/`BETWEEN`, a bounded timestamp interval, regex, and
LIKE patterns whose result is independent of collation (`/%`, `%*%`).
The SQL Server emitter lowers only a fixed bounded ASCII regex subset under a
binary collation (`^[0-9a-f]{64}$`, SHA-256-prefixed hashes, bounded ASCII
identifiers, and digits); other regex patterns remain blocked.
Function calls, subqueries, collation-bearing LIKE, JSON operators and
PostgreSQL `IS DISTINCT FROM` remain blocked rather than approximated.

**Comments:** PostgreSQL and Oracle use the portable `COMMENT ON TABLE/COLUMN`
spelling. MySQL table comments use `ALTER TABLE ... COMMENT = ...`; MySQL
column comments need a complete `MODIFY`/`CHANGE` definition and therefore
remain blocked in the one-statement profile without a column catalogue. SQL
Server has no equivalent statement; with an explicit target schema it uses
`sys.sp_addextendedproperty` at the schema, table, and optional column levels,
and refuses values over 7,500 bytes. Without that schema mapping, the comment
remains blocked because SQL Server's object-level metadata scope is ambiguous.

**CREATE INDEX:** name, target table, plain column list with preserved
`DESC` ordering, optional `UNIQUE`. PostgreSQL and SQL Server preserve typed
partial/filtered predicates (`WHERE`) and `INCLUDE`; the portable `btree`
method is rendered in the target's correct position. Other access methods,
unsupported target combinations, and `NULLS FIRST/LAST` remain blocked
because their semantics or rerun behavior do not have one exact four-dialect
profile.
Standalone index and constraint statements do not carry the referenced column
types. A context-aware caller may pass a source catalogue through
`translate_ddl(..., catalog=...)`; known MySQL `TEXT` key columns then fail
closed instead of emitting server-rejected DDL, while an unknown catalogue
entry remains unknown and is never treated as proof of safety.

Anything else -- generated/computed columns, JSONB/arrays without an exact
target route, partitioning, storage options, unsupported trigger targets,
RLS, dynamic SQL, transaction control, exception-heavy procedures, DEFAULT
expressions outside the typed allowlist, CHECK with a non-portable
function/operator, or multiple statements per call -- raises `DialectError`
and is reported as `BLOCKED`. This is deliberate and covered by tests (see
`test_out_of_scope_ddl_fails_closed_instead_of_guessing`).

## certified-routine-v1 (stored functions and procedures)

The routine profile uses the real sqlglot AST and a closed typed routine IR.
Its scalar subset has typed parameters, one scalar return type, and one
dollar-quoted SELECT expression. The expression may contain declared
parameters, literals, arithmetic, concatenation, CHR/CHAR code points,
COALESCE, LOWER, UPPER, TRIM, and ABS. Emitters produce native PostgreSQL,
MySQL, Oracle PL/SQL, and T-SQL function definitions; Oracle and T-SQL
procedural DDL receives the strongest local syntax check available from the
pinned parser, with real target execution still separate evidence.

The expansion also contains typed bounded OUT/INOUT assignment procedures,
single-SELECT `RETURNS TABLE` functions on their explicit PostgreSQL/T-SQL
route, and trigger metadata with a PostgreSQL-only target route. The parser
retains schema, `OR REPLACE`, stability, STRICT, SECURITY DEFINER, and
`SET search_path` facts, but refuses them when no exact mapping is supplied.
PL/pgSQL side effects, table reads, query DML, control flow, exception
handling, dynamic SQL, transaction control, RLS and target-specific security
behavior receive explicit blocker codes; they are never relabelled as
converted scalar functions. Fixed-column literal `INSERT ... VALUES`, bounded
single-source `INSERT ... SELECT`, and single-table `UPDATE` are handled by
the typed DML profiles; joins, conflict policies and volatile expression
values remain blocked.

    uv run elmos-sql-dialect translate \
      --source-file function.sql --source-dialect postgres \
      --target-dialect mysql --statement-kind FUNCTION --output out/

In the current real corpus, 47 PL/pgSQL routines, 12 table-returning
functions, 8 target-specific trigger definitions, 7 unsupported parameter
signatures, 4 security-context routines, and 21 schema-qualified routine
definitions or privileges remain explicit blockers. The scanner keeps all of
them in the denominator and gives each an explicit manual or source-review
disposition.

## Why not just use sqlglot's own generator

Parsing uses `sqlglot` 30.14.0 (pinned), a real, mature, dialect-aware SQL
parser -- the same "real compiler frontend, not string templates" choice
this repository already made elsewhere (JDK Tree API, Roslyn, CPython AST,
TS Compiler API in `engines/polyglot-route-engine`). But sqlglot's own
built-in cross-dialect generator (`sqlglot.transpile` / `.sql(dialect=)`)
has real, reproduced correctness gaps for exactly the constructs this
profile cares most about: it passes MySQL's `AUTO_INCREMENT` through
verbatim into Oracle output (invalid syntax there), and it passes SQL
Server's `IDENTITY(1,1)` through into MySQL output (also invalid). Trusting
that generator directly would silently violate the fail-closed contract.

So this engine uses sqlglot only for parsing (source dialect -> AST) and for
syntax-validation re-parsing (emitted SQL -> re-parse in strict target-
dialect mode). Emission goes through a hand-written, per-vendor renderer
(`dialects.py`) that is unit-tested against the exact bugs above -- every
one of the 31 tests in `tests/test_certified_ddl_v1.py` asserts the correct
target-dialect keyword appears and the wrong one does not.

## certified-alter-v1 (ALTER TABLE)

A second profile, added because the first coverage scan showed the gap was
structural: 128 of the repository's statements were `ALTER TABLE`, which
`certified-ddl-v1` did not address at all.

Scope was chosen by measurement, not intuition. Of 635 real ALTER actions:
603 `ADD COLUMN`, 29 `ADD CONSTRAINT`, 2 `RENAME COLUMN`, 1
`DROP CONSTRAINT`. Those five operations are the profile:

- `ADD COLUMN`, with the same certified column model as `CREATE TABLE`
  (type, nullability, literal default, inline `REFERENCES`, inline `CHECK`)
- `DROP COLUMN`
- `RENAME COLUMN`
- `ADD CONSTRAINT` — `PRIMARY KEY` / `UNIQUE` / `FOREIGN KEY` / `CHECK`
- `DROP CONSTRAINT`

```bash
uv run elmos-sql-dialect translate \
  --source-file alter.sql --source-dialect postgres \
  --target-dialect oracle --statement-kind ALTER --output out/
```

### The boundary that matters

`ALTER COLUMN TYPE`, `SET NOT NULL`, `SET DEFAULT` and `DROP DEFAULT` are
**refused**. MySQL spells a column change `MODIFY c <TYPE> NOT NULL` and
SQL Server `ALTER COLUMN c <TYPE> NOT NULL` — **both require the column's
full type to be restated**, and an `ALTER TABLE t ALTER COLUMN c SET NOT
NULL` statement does not carry it. This engine reads one statement at a
time with no catalog to look the type up in, so emitting those targets
would mean inventing a type. That is exactly the silent corruption the
profile exists to prevent. They appeared 0 times in the corpus, so
refusing them costs nothing measurable.

### Two rules the validator cannot enforce

`sqlglot` accepts both of these without complaint, and the real databases
reject them. A permissive parser means the syntax-validation leg proves
nothing here, so the rules live in the emitter and are pinned by tests —
the same posture already taken for sqlglot's AUTO_INCREMENT/IDENTITY
generation defect:

| Rule | Why |
|---|---|
| **Oracle never gets `ADD COLUMN`** | Oracle has no such keyword; it is `ALTER TABLE t ADD (c ...)`. |
| **SQL Server never gets `RENAME COLUMN`** | T-SQL has no such clause; it requires `EXEC sp_rename 't.c', 'new', 'COLUMN'` — a different statement kind entirely. |

Multi-action statements are emitted as separate statements rather than a
comma list, because Oracle's parenthesised `ADD` cannot be mixed with
other action kinds.

## Find out the coverage BEFORE migrating

A certified subset is only honest if its boundary is visible in advance.
`scan` answers "how much of this schema can actually be translated?"
without writing anything or even picking a target dialect:

```bash
uv run elmos-sql-dialect scan \
  --repository ./my-service/src/main/resources/db/migration \
  --source-dialect postgres \
  --output ./feasibility
```

Statements are split by **sqlglot itself**, not by splitting on
semicolons -- a semicolon inside a string literal, a `$$`-quoted function
body or a `BEGIN ... END` block would otherwise miscount silently. Both
`feasibility-report.json` and `feasibility-report.md` are written.

Use `--require-disposition-complete` when the gate you need is the 100%
repository-coverage check. It succeeds only when every discovered unit has a
known disposition and there are no scanner defects; it does not make blocked
SQL translatable or certify an external database migration.

Read the **`Distinct`** column, not just the count. A blocker with 342
occurrences but 3 distinct reasons is one idiom copy-pasted across a
schema; widening the subset for it buys far less than the raw count
suggests. That column exists because the first real scan got this wrong.

Everything executable stays in the denominator. Unlike the component
engine's scanner -- where a function returning no JSX is a helper rather
than a migration unit -- an `ALTER TABLE`, view or stored procedure IS
work the customer needs done, so excluding it would flatter the ratio by
hiding exactly what this engine cannot do.

### What it says about real code

Run against the current checkout's 76 migration files, the scan reports
**1173 of 1485 statements as automatic translation candidates (79.0% upper
bound)**, counting all active profiles. It also reports **1485 of 1485 (100.0%)
with an explicit disposition**: 1173 automatic candidates, 303 manual
migrations, and 9 source-format reviews.

The automatic candidate number is intentionally conservative. The blocker
ranking says why, while the disposition ledger ensures no unit disappears:

| Blocker | Occurrences | Distinct | What it really is |
|---|---|---|---|
| `CERTIFIED_DDL_UNSUPPORTED_STATEMENT` | 142 | 1 | anonymous DO blocks, RLS toggles and other statements have no common portable route |
| `CERTIFIED_ROUTINE_UNSUPPORTED_LANGUAGE` | 47 | 1 | PL/pgSQL side effects/control flow cannot be lowered to the bounded routine IR |
| `CERTIFIED_DDL_UNSUPPORTED_IDENTIFIER_SHAPE` | 24 | 6 | expression indexes and computed/qualified CHECK operands remain typed blockers |
| `CERTIFIED_ROUTINE_NAMESPACE_MAPPING_REQUIRED` | 21 | 1 | schema-qualified routine names and privileges need an explicit target namespace mapping |
| `CERTIFIED_DDL_UNBOUNDED_DECIMAL` | 15 | 1 | arbitrary-precision DECIMAL/NUMBER has no fixed cross-dialect equivalent |
| `CERTIFIED_ROUTINE_TABLE_RETURN_UNSUPPORTED` | 12 | 1 | table-returning functions outside the simple typed SELECT shape remain blocked |
| `CERTIFIED_DDL_PARSE_FAILED` | 9 | 9 | source-format/parser review remains required |
| `CERTIFIED_ROUTINE_TRIGGER_UNSUPPORTED` | 8 | 1 | trigger definitions outside the explicit target route need timing/action semantics |
| `CERTIFIED_RLS_TARGET_ROUTE_REQUIRED` | 7 | 1 | RLS requires a target policy model; it is never weakened to an open policy |
| `CERTIFIED_ROUTINE_UNSUPPORTED_PARAMETER` | 7 | 2 | unsupported parameter shapes need a target-specific callable contract |
| `CERTIFIED_DDL_UNSUPPORTED_TYPE` | 5 | 1 | residual vendor-specific/return types remain outside the certified set |
| `CERTIFIED_ROUTINE_SECURITY_CONTEXT_UNSUPPORTED` | 4 | 1 | SECURITY DEFINER/search_path changes execution identity or name resolution |
| `CERTIFIED_UPDATE_COLUMN_TYPE_UNPROVEN` | 3 | 1 | source/target assignment types are not both proven by the source catalogue |
| `CERTIFIED_INSERT_UNSUPPORTED_MODIFIER` | 3 | 1 | conflict/upsert semantics need a target-specific route |
| `CERTIFIED_DDL_UNSUPPORTED_CHECK` | 3 | 2 | residual CHECK expression semantics are not in the typed predicate profile |
| `CERTIFIED_DDL_UNSUPPORTED_DEFAULT` | 1 | 1 | a non-literal default remains outside the typed default profile |
| `CERTIFIED_DML_UNSUPPORTED_EXPRESSION` | 1 | 1 | volatile `clock_timestamp()` and other expressions remain outside the typed DML profile |

The first run of this scan reported **8.0%**, and reading it found a real
defect rather than a subset limit: inline `b_id INTEGER REFERENCES b(id)`
was rejected while the semantically identical table-level
`FOREIGN KEY (b_id) REFERENCES b(id)` was accepted. Every one of the four
dialects treats those two spellings identically, so producing different
canonical models for them was simply wrong. Fixing it -- and lifting
inline `CHECK` the same way -- moved 8.0% to 10.3% and is locked down by
tests asserting the two spellings produce an identical model.

The historical 64-file snapshot was 174/1015 = 17.1%. Subsequent typed
expansions now cover schema-qualified objects with explicit mapping, safe
OR REPLACE cases, view/query metadata, callable and constraint comments, table
privileges, bounded procedures, table-valued functions, trigger metadata,
JSON/plain binary routes, unbounded PostgreSQL `BYTEA` to target LOB mappings,
the typed JSONB literal-default profile, literal-only INSERT seeds, bounded
single-source/equi-join `INSERT ... SELECT`, simple single-table `UPDATE`, and
a typed `UPDATE ... FROM` route gated by a source PRIMARY KEY/UNIQUE proof and
matching catalogue types, PostgreSQL adjacent-string comment recovery, and the earlier
CHECK/identity/precision work. The current checkout therefore measures
**1173/1485 = 79.0%** automatic candidates. The repository-
level headline remains **1485/1485 = 100.0% disposition coverage**: every
blocker is explicit manual or source-review work, and none is silently
converted.

## Local run

```bash
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check src tests
uv run --locked --extra dev mypy --ignore-missing-imports src
```

`--locked` rather than a free resolve: `uv.lock` is committed and pins
`sqlglot` to 30.14.0 with a hash. This engine deliberately does not use
sqlglot's own cross-dialect generator because of defects reproduced
against that exact version, and its `_TYPE_MAP` is keyed on that version's
`DataType.Type` members — so a silently different resolve could change
translation results without any source change.

Or with plain pip (no `uv` required):

```bash
pip install -e ".[execution,dev]"
pytest tests/ -v
ruff check src tests
mypy --ignore-missing-imports src
```

## CLI usage

```bash
uv run elmos-sql-dialect translate \
  --source-file customers.sql \
  --source-dialect mysql \
  --target-dialect postgres \
  --statement-kind TABLE \
  --output out/
```

Writes `out/translation-report.json` (full evidence: status, syntax/
execution validation results, diagnostics) and, when `status: "PASSED"`,
`out/emitted.sql`. Exit code is `0` on `PASSED`, `2` on `BLOCKED` or
`FAILED`. `--statement-kind INDEX` switches to `CREATE INDEX` mode.

## Validation: two independent legs

Every translation runs **syntax validation** unconditionally: the emitted
DDL is re-parsed by sqlglot in strict target-dialect mode, so a
canonical-model bug that produces syntactically invalid target SQL is
caught immediately rather than trusted on faith.

**Execution validation** additionally runs a real database when a DSN is
supplied and the target is Postgres or MySQL (`EXECUTABLE_DIALECTS`):
```bash
uv run elmos-sql-dialect translate ... --target-dialect postgres \
  --dsn "host=127.0.0.1 dbname=postgres user=postgres" --output out/
uv run elmos-sql-dialect translate ... --target-dialect mysql \
  --dsn '{"host":"127.0.0.1","port":3306,"user":"root","password":""}' --output out/
```
Postgres validation runs the emitted `CREATE TABLE`, `CREATE INDEX`, or
routine definition inside a
transaction that is always rolled back; MySQL validation creates a
throwaway database, runs the statement, and always drops it -- neither
leaves state behind, win or lose. Oracle and SQL Server have no freely
licensed, root-less local server available in most environments, so
execution validation for those two targets is always
`EXECUTION_NOT_AVAILABLE`, even with `--dsn` supplied -- syntax validation
is the full evidence available for those two dialects today.

**Honest sandbox disclosure:** the code paths above are real (real
`psycopg2`/`PyMySQL` calls, not stubs) and are exercised by tests for
control flow (`test_execution_validation_reports_not_attempted_without_dsn`,
`test_execution_validation_reports_not_available_for_oracle_and_tsql_even_with_dsn`).
They were **not** exercised end-to-end against a live Postgres/MySQL server
inside the development sandbox used to build this engine, because that
sandbox has no root/sudo access and no `aarch64` Linux wheel exists for an
embeddable Postgres server. If you run this with a real `--dsn` pointed at
your own Postgres or MySQL instance, you are the first real execution of
that code path -- please report anything that doesn't match the syntax-only
result.

## Deployment

This is a library/CLI, not a running service -- there is nothing to deploy
as a container. Install it (`pip install -e .` or build a wheel with
`uv build`) wherever DDL translation is needed: a CI step validating a
migration script before it ships, a local developer tool, or invoked as a
subprocess from another engine the same way `engines/polyglot-route-engine`
is bridged into `modules/lowering` (see `PolyglotRouteEngineBridge.java` for
that pattern). No network service, no database credentials are required
unless you opt into execution validation with `--dsn`.

## Status

The certified profiles are `EXPERIMENTAL`. All 438 repository-owned tests pass locally
(`uv run pytest`), `ruff check` and `mypy` are clean. Independent/external
certification of this profile is `NOT_RUN`, consistent with how this
repository reports certification status for its other engines.
