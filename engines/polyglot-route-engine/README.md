# ELMOS Polyglot Route Engine

This engine implements a compiler-backed, fail-closed vertical slice across Java,
Python, C#, TypeScript, C++, Objective-C and Swift. Every directed pair is
independent.

All seven are both source and target, so the profile carries 42 directed
routes. Swift source analysis goes through a SwiftSyntax helper under
`native/swift`, built on demand by `swift build -c release` the first time a
Swift route runs -- the same on-demand build the TypeScript CLI already uses.

The helper is built against the `exact:` swift-syntax pin in
`native/swift/Package.swift` (currently `600.0.1`). swift-syntax's major tracks
the Swift release it ships with (5.10 -> 510.x, 6.0 -> 600.x), so on a host
whose `swiftc --version` reports a different release, move that one line to the
matching major and record the pairing here. A mismatched pin fails the build
loudly rather than resolving to whatever is newest, the same posture as
`ELMOS_SWIFT_VERSION` in `toolchains.py`.

One detail of the Swift frontend is easy to get wrong and worth stating.
SwiftSyntax deliberately does *not* apply operator precedence while parsing:
`a + b * c` arrives as a single flat `SequenceExprSyntax`, and
`InfixOperatorExprSyntax` only exists after a separate folding pass. The
analyzer therefore folds with `OperatorTable.standardOperators` from
`SwiftOperators` -- the compiler's own precedence table -- rather than a
hand-rolled precedence ladder, so `a - b - c` and `a + b * c` associate exactly
as `swiftc` associates them. A fold the table cannot resolve fails closed with
`SWIFT_OPERATOR_FOLDING_FAILED` instead of leaving an unfolded sequence to be
misread downstream.

C++ and Objective-C are lifted from clang's own AST
(`clang -Xclang -ast-dump=json -fsyntax-only`), so the IR carries the types
clang resolved rather than a guess at them. Both share one analyzer because for
this profile they differ in exactly three places: the boolean spelling
(`bool` / `BOOL`), the string type (`std::string` / `NSString *`), and how a
string operation appears in the tree (`CXXOperatorCallExpr` / `ObjCMessageExpr`).

The `typed-pure-function-v1` profile supports explicit primitive parameter and
return types, literals, identifiers, selected binary operators, `if`, and
`return`. Java uses the JDK Compiler Tree API, Python uses CPython AST, C# uses
Roslyn, and TypeScript uses the TypeScript Compiler API. Every emitted target is
compiled by its native toolchain and executed against the same behavior cases.

Unsupported statements, expressions, types, async behavior, side effects,
frameworks, databases, concurrency, reflection, and I/O fail closed. This exact
profile is `LIMITED`: the directed routes pass native analysis, target compilation,
separate holdout, and representative behavior replay. Independent and external
certification remain `NOT_RUN`; repository orchestration never broadens this
semantic boundary.

## Canonical types and operator semantics

The IR has four canonical types. `integer` is a **64-bit signed integer** and
`number` is **IEEE-754 binary64**; those two definitions are what every route
is checked against.

| Canonical | java | python | csharp | typescript | cpp | objc | swift |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `integer` | `long` | `int` | `long` | `number` | `std::int64_t` | `long long` | `Int` |
| `number` | `double` | `float` | `double` | `number` | `double` | `double` | `Double` |
| `boolean` | `boolean` | `bool` | `bool` | `boolean` | `bool` | `BOOL` | `Bool` |
| `string` | `String` | `str` | `string` | `string` | `std::string` | `NSString *` | `String` |

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
* C++'s `const std::string &` lifts to canonical `string`: for a pure function
  the reference qualifier is not observable, and const-reference is the
  idiomatic way to pass a string.
* `float` is refused in C++ and Objective-C for the same reason as in Java and
  C#; `unsigned` types are outside the canonical set entirely.

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

Equality and ordering are typed the same way. `==`/`!=` on `string` emits
`.equals(...)` in Java (`==` there compares references), `===`/`!==` in
TypeScript, and `[a isEqualToString:b]` in Objective-C (`NSString *` is a
pointer, so `==` compares addresses); `+` on `string` becomes
`[a stringByAppendingString:b]` there, because NSString has no `+` at all.
C++ and Swift need neither rewrite -- `std::string` and `String` compare and
concatenate by value. `<`/`<=`/`>`/`>=` on `string` fails closed everywhere,
because Java orders by UTF-16 code unit and Python by code point.

In the other direction, an Objective-C **source** writing `a == b` on two
`NSString *` is refused
(`OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET`): that expression
means pointer identity, which no other target can express, and lifting it as
value equality would change the program.

C++, Objective-C and Swift all truncate `/` and `%` toward zero, so the
canonical operators map straight through -- only Python needs the emitted
helpers.

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

clang and Swift ship with Xcode (or a platform toolchain) rather than from a
fixed URL, so their exact build differs per machine and the pin is read from
the environment instead of being hard-coded. Declare it once per host:

```bash
export ELMOS_CLANG_VERSION="$(clang --version | head -1)"
export ELMOS_SWIFT_VERSION="$(swiftc --version | head -1)"
```

An unset pin is a hard block (`EXACT_TOOLCHAIN_PIN_MISSING`), exactly like a
mismatch: "whatever is installed" is never accepted as evidence.

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
uv run elmos-polyglot-route repository-preflight \
  --repository /approved/read-only/workspace \
  --repository-ref local:customer-repository \
  --source-language java \
  --target-language python \
  --output /durable/tenant-job/preflight.json

uv run elmos-polyglot-route repository-pipeline \
  --repository /approved/read-only/workspace \
  --repository-ref local:customer-repository \
  --source-language java \
  --target-language python \
  --cases-directory /approved/independent-cases \
  --output /durable/tenant-job/pipeline
```

`repository-preflight` performs only stable repository planning and declaration
inventory. It never runs native analyzers, emission, behavior cases or builds.
The 10,000 limit is a per-task reported-row capacity, not a claim about the
actual number of functions in an inventory-incomplete language. Python AST
inventory reports an exact count. Other language scanners return
`PASSED_WITH_INCOMPLETE_INVENTORY`, `count_complete=false`, a reported-row lower
bound and `actual_obligation_count_status=UNKNOWN`; their final report remains
INDETERMINATE with an UNKNOWN scope blocker. At the 10,001st reported row,
preflight returns a content-addressed `REJECTED` sentinel without continuing an
unbounded count. Trusted business results exit zero; unsafe paths, digest drift
and output integrity failures remain non-zero. The formal pipeline repeats the
plan and inventory and rejects any later snapshot drift.

The output directory is a durable checkpoint boundary. Re-running the command
recomputes inventory and discovery from the read-only source, detects source
drift, resumes the per-unit batch checkpoint, rebuilds assembly from verified
bytes, and emits `repository-migration-artifact.zip` with an exact file/digest
manifest. `COMPLETE` requires every functional obligation to pass; missing
behavior cases, unsupported units or failures produce `PARTIAL` when verified
target code remains or `BLOCKED` at zero verified functions, and stay visible
in the pipeline report. Local execution never changes independent or external
evidence from `NOT_RUN`.

Every normally finalized pipeline also writes two content-addressed functional
reports, even when no target function succeeds:

- `functional-conversion-report.json` is the machine-readable authority.
- `FUNCTION_CONVERSION_REPORT.md` is derived from that JSON and contains the
  source/target code comparison, failure reason and deterministic next actions
  for every unsuccessful obligation. Reports with more than 2,000 obligations
  are written as up to five content-addressed JSON/Markdown shards plus a root
  index and deterministic download bundle; the aggregate is recomputed from
  every shard and no obligation is represented by a capacity sentinel. More
  than 10,000 reported obligation rows fail closed before native analysis or emission with
  `FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED` and require an explicit campaign split.

The success-rate numerator contains only functions whose emitted target passed
the declared behavior oracle **and** whose assembled target project passed its
real build. For a compiler-complete inventory, the denominator contains every
identified callable; `FAILED`, `UNSUPPORTED` and `NOT_RUN` are never removed.
A source unit whose declarations are not compiler-completely enumerable adds
an explicit `UNKNOWN_SOURCE_UNIT`, sets `denominator_complete=false`, and makes
the project-level result `INDETERMINATE`. In that case the exact `N/D` and
percentage are labelled only as the known-scope diagnostic, while the main
result is an honest range with the unknown scope and its remediation described;
one file-level sentinel is never presented as the number of missed functions.
For measured inventories, basis points use floor division, so `2/3` is
displayed as `66.66%`, never rounded up.

A single report contains at most 2,000 obligation rows. A bounded run may contain
up to 10,000 rows across at most five exact shards. Every report file is capped
at 64 MiB and a sharded deterministic bundle at 256 MiB. Embedded excerpts use
a 4 MiB global budget. A truncated or omitted excerpt still retains the exact
full-block byte/line range, full-block digest, document digest, extraction
method and a machine-readable omission reason; Markdown prints those identifiers
before the comparison. Only a target that was never generated has no target
range and is explicitly marked `NOT_GENERATED`.

A zero-success or build-blocked run has `status=BLOCKED`, keeps the two report
files downloadable to its authorized tenant, and does not expose a code ZIP.
Paths, symlinks, source/case drift, corrupt checkpoints and digest mismatches
remain hard integrity failures and do not authorize a newly generated report.
The comparison basis is `DECLARED_BEHAVIOR_ORACLE`: a VERIFIED obligation must
pass the same declared cases in the extracted source function and generated
target function, then pass the whole-target-project build. This is bounded case
evidence only; full source-versus-target semantic/runtime equivalence,
independent verification and certification remain `NOT_RUN` / `NOT_CERTIFIED`.
The source snapshot and the complete behavior-case manifest are re-inventoried
at pipeline completion; addition, deletion, rename or byte drift is a hard
integrity failure and cannot publish a new final report or code archive.

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
