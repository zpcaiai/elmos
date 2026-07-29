# ELMOS Polyglot Route Engine

This engine implements a compiler-backed, fail-closed vertical slice across Java,
Python, C#, and TypeScript. Every directed pair is independent.

The `typed-pure-function-v1` profile supports explicit primitive parameter and
return types, literals, identifiers, selected binary operators, `if`, and
`return`. Java uses the JDK Compiler Tree API, Python uses CPython AST, C# uses
Roslyn, and TypeScript uses the TypeScript Compiler API. Every emitted target is
compiled by its native toolchain and executed against the same behavior cases.

Unsupported statements, expressions, types, async behavior, side effects,
frameworks, databases, concurrency, reflection, and I/O fail closed. This exact
profile is `LIMITED`: all 12 directions pass native analysis, target compilation,
separate holdout, and representative behavior replay. Independent and external
certification remain `NOT_RUN`; repository orchestration never broadens this
semantic boundary.

## Canonical types and operator semantics

The IR has four canonical types. `integer` is a **64-bit signed integer** and
`number` is **IEEE-754 binary64**; those two definitions are what every route
is checked against.

| Canonical | java | python | csharp | typescript |
| --- | --- | --- | --- | --- |
| `integer` | `long` | `int` | `long` | `number` |
| `number` | `double` | `float` | `double` | `number` |
| `boolean` | `boolean` | `bool` | `bool` | `boolean` |
| `string` | `String` | `str` | `string` | `string` |

Lifting *into* those types is deliberately narrower than each language's own
type system, because the difference is not observable in the emitted code:

* `byte`/`short`/`int` (Java, C#) widen to the 64-bit `integer`. Exact for
  every value; only 32-bit overflow wraparound differs, and that difference is
  unobservable in the pure-function profile unless the source relies on it.
* `float`/`Single` is **refused** (`JAVA_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET`,
  `CSHARP_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET`): a 24-bit significand does
  not round-trip through binary64 -- `0.1f + 0.2f != 0.1 + 0.2`.
* `BigDecimal`/`BigInteger`/`decimal` is **refused**: exact base-10 arithmetic
  has no binary floating-point equivalent in any target here.
* Java's boxed wrappers (`Integer`, `Long`, `Double`, `Boolean`, ...) are
  **refused**: they are nullable and the certified subset has no null.
* TypeScript's `number` lifts to canonical `number`, never `integer` -- the
  language has no integer type.

Operators are typed, not textual. The canonical `/` and `%` on two `integer`s
are the **truncating** pair (Java/C#/TypeScript semantics), so:

* a Python **target** gets `_elmos_truncating_div` / `_elmos_truncating_mod`
  helpers instead of `/` and `%` (Python's `//` floors and its `%` follows the
  sign of the divisor: `-7 // 2` is `-4` and `-7 % 2` is `1`, where Java
  answers `-3` and `-1`), and `math.fmod` for float remainder;
* a TypeScript **target** gets `Math.trunc(a / b)`, since `/` there is float
  division;
* a Python **source** using `/` on two ints, or `%` at all, fails closed
  (`PYTHON_TRUE_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET`,
  `PYTHON_FLOORED_MODULO_OUTSIDE_CERTIFIED_SUBSET`) -- those spellings mean
  something the canonical operator does not.

Equality and ordering are typed the same way: `==`/`!=` on `string` emits
`.equals(...)` in Java (`==` there compares references) and `===`/`!==` in
TypeScript, while `<`/`<=`/`>`/`>=` on `string` fails closed, because Java
orders by UTF-16 code unit and Python by code point.

Literals are range-checked per target: an `integer` literal outside int32 gets
the `L` suffix in Java/C# (without it `javac` reports "integer number too
large"), a literal beyond 2^53-1 is refused for a TypeScript target
(`number` cannot hold it exactly), a literal outside int64 is refused
everywhere, and NaN/Infinity have no shared spelling and are refused.

Runtime values are guarded too: an emitted TypeScript function that carries
`integer` parameters or returns one checks each of them with
`Number.isSafeInteger` and throws `RangeError: ELMOS_INTEGER_NOT_SAFE:<value>`
instead of continuing with a silently rounded value. The helper is emitted
only when a function actually carries an `integer`; `number`-only functions
are untouched, and the other three targets need no guard because `long`/`int`
hold the whole canonical range exactly.

The one boundary that stays documented rather than enforced: Java's and C#'s
`byte`/`short`/`int` widen to the 64-bit canonical `integer`, so a source that
*relies on* 32-bit overflow wraparound translates into code that does not wrap
at the same point. Rejecting `int` outright would exclude most real Java and
C# for a behaviour the pure-function profile has no way to observe, so this is
a stated limit of `typed-pure-function-v1`, not a silent one.

Execution is exact-toolchain bound: Java 21.0.11, Python 3.12.12, .NET SDK
10.0.301 / Roslyn 5.6.0, and TypeScript 5.9.2 on Node 26.0.0. A missing or
different source or target toolchain blocks the route instead of accepting
language-level compatibility flags as equivalent evidence.

```bash
uv sync --locked
uv run pytest
uv run ruff check src tests
uv run mypy src
```

## Repository inventory and decomposition

Repository scope starts with a bounded, read-only inventory. It does not execute
customer code and does not infer repository-wide migration success from the
pure-function profile:

```bash
uv run elmos-polyglot-route inventory \
  --repository /approved/read-only/workspace \
  --repository-ref local:customer-repository \
  --source-language java \
  --target-language python \
  --output repository-route-plan.json
```

The command ignores known build/vendor directories, never follows symbolic
links, verifies that every accepted file stays stable while read, and enforces
file-count, per-file, and aggregate byte limits. Its content-addressed output
contains one `DISCOVERY_REQUIRED` work unit per source file. Every work unit
keeps execution at `NOT_RUN` until a function name and independent behavior-case
corpus are supplied; framework, database, I/O, concurrency, exceptions, async
and object-graph semantics remain explicit blockers.

`discover` classifies every work unit with a precise verdict (`READY`,
`UNSUPPORTED`, `NO_CANDIDATE_DECLARATION`, `UNREADABLE`) using the same
compiler-backed analyzer the migration itself uses -- a candidate name is
proposed cheaply but never accepted without that analyzer's confirmation.
`batch` then attempts only `READY` units that also have a matching
`{unit_id}.json` behavior-case file under `--cases-directory`, resumably via a
`batch-checkpoint.jsonl`, and never rounds a partial run up to `COMPLETE`.

## Whole-project assembly

A batch run proves each work unit in isolation. Every `PASSED` unit reuses the
same fixed emitted file name (`Migrated.java` / `Migrated.cs` / `migrated.py` /
`migrated.ts`, and for Java/C# the same class name too), so combining two units
verbatim would collide on the first duplicate -- a batch report by itself is
not a project anyone can build. `assemble` closes that gap for one already-run
batch report:

```bash
uv run elmos-polyglot-route assemble \
  --batch-report batch/batch-report.json \
  --batch-output batch \
  --destination assembled-library \
  --verify
```

For every `PASSED` unit it re-verifies the unit's recorded sha256 against the
batch output on disk (defense in depth against a tampered or stale batch
directory), then places the unit's already-emitted source under a per-unit
namespace -- a Java/C# package/namespace per unit, a Python/TypeScript module
per unit -- so nothing collides, and writes a real per-language build manifest
(`pom.xml` / a root `.csproj` / `pyproject.toml` / `package.json` +
`tsconfig.json`). `FAILED` and `SKIPPED_*` units are recorded, with their
reason, in `assembly-manifest.json` under `excluded_units`; they are never
silently dropped and never included in the assembled project.

`--verify` (or a separate `verify_assembled_project` call) runs a real
whole-project compile/build check with the same exact-toolchain contract the
per-unit harness already enforces (`javac` across all sources, `python -m
compileall`, `dotnet build`, or `tsc`), and only on success writes local-run
and cloud-publishing guidance (`docs/LOCAL_RUN.md`, `docs/CLOUD_PUBLISHING.md`,
`deploy/deployment-options.json`) into the assembled project. The assembled
artifact is a library of certified pure functions, not a running service, so
that guidance documents a real build + package-publish workflow (recommending
AWS CodeArtifact, since it is the one platform that natively covers all four
target package formats) rather than a Cloud Run-style container deployment.

Units are never merged into one shared namespace even when the build passes:
two different source files can define a same-named function with different
behavior, and assembly does not attempt to resolve that at the semantic level.
Callers must import each unit by its own id/module, not assume a combined API.
Independent verification and external certification remain `NOT_RUN` /
`NOT_CERTIFIED` regardless of local build success.

## Resumable repository pipeline

`repository-pipeline` composes inventory, compiler-backed discovery, resumable
per-unit execution, collision-safe assembly, and a real whole-project build into
one operator command:

```bash
uv run elmos-polyglot-route repository-pipeline \
  --repository /approved/read-only/workspace \
  --repository-ref local:customer-repository \
  --source-language java \
  --target-language python \
  --cases-directory /approved/independent-cases \
  --output /durable/tenant-job/pipeline
```

The output directory is a durable checkpoint boundary. Re-running the command
recomputes inventory and discovery from the read-only source, detects source
drift, resumes the per-unit batch checkpoint, rebuilds assembly from verified
bytes, and emits `repository-migration-artifact.zip` with an exact file/digest
manifest. `COMPLETE` requires every work unit to pass; missing behavior cases,
unsupported units or failures produce `PARTIAL` and remain visible in the
pipeline report. Local execution never changes independent or external evidence
from `NOT_RUN`.

## Single-declaration bridging (`emit` / `check`)

`migrate` is atomic (analyze -> emit -> validate against behavior cases), which
fits this engine's own repository pipeline but not every caller. `emit` and
`check` decompose that into two real, narrower primitives for callers that
handle emission and validation as separate steps with no behavior-case corpus
of their own -- specifically `modules/lowering`'s `TargetEmitter`/
`StaticValidator`, which delegate here via subprocess rather than reinventing
a second translation backend (see `PolyglotRouteEngineBridge.java` and
ADR-0023's addendum).

```bash
uv run elmos-polyglot-route emit \
  --source Calc.java --source-language java --target-language csharp \
  --function calculate --output emitted/

uv run elmos-polyglot-route check \
  --target-language csharp --file emitted/Migrated.cs --output checked/
```

`emit` runs the same real analyzer and emitter as `migrate`, with no
compilation and no execution; it needs only the *source* language's exact
toolchain. `check` compiles/type-checks one already-emitted file alone -- no
harness, no execution -- using the *target* language's exact toolchain; it is
deliberately narrower than `validate`, which requires behavior cases and
actually runs the code. Both fail closed exactly like the rest of this
engine: an unsupported construct, a same-language route, or a
missing/mismatched toolchain raises `RouteError` rather than a degraded
success.
