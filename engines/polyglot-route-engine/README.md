# ELMOS Polyglot Route Engine

This engine implements a compiler-backed, fail-closed vertical slice across Java,
Python, C#, TypeScript, Go, Rust, C++, Objective-C and Swift. Every attempted
direction is evaluated independently; no reverse or Cartesian route is inferred.

All nine have source inventory, candidate discovery and target-project assembly
plumbing. The repository capability inventory explicitly lists all 72 ordered
language pairs; it never infers an unlisted direction and a route record is not
a certification claim. Evidence provenance remains split between the original
six-language complete 30, the C++/Objective-C/Swift/Java specialised exact
eight, and the remaining 34 local capability routes. Only the exact eight carry
the additional module, concrete-span, behaviour and SMT obligations described
below. Swift source analysis goes through a SwiftSyntax helper under
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
profile is `LIMITED`: only a route whose persisted evidence says
`PASSED_LOCAL` has passed native analysis, target compilation, separate
holdout, and representative behavior replay. Other declared routes remain
`NOT_RUN`. Independent and external certification remain `NOT_RUN`;
repository orchestration never broadens this semantic boundary.

## Canonical types and operator semantics

The IR has four canonical types. `integer` is a **64-bit signed integer** and
`number` is **IEEE-754 binary64**; those two definitions are what every route
is checked against.

| Canonical | java | python | csharp | typescript | go | rust | cpp | objc | swift |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `integer` | `long` | `int` | `long` | guarded `number` | `int64` | `i64` | `std::int64_t` | `long long` | `Int64` |
| `number` | `double` | `float` | `double` | `number` | `float64` | `f64` | `double` | `double` | `Double` |
| `boolean` | `boolean` | `bool` | `bool` | `boolean` | `bool` | `bool` | `bool` | `BOOL` | `Bool` |
| `string` | `String` | `str` | `string` | `string` | `string` | `String` | `std::string` | `NSString *` | `String` |

Lifting *into* those types is deliberately narrower than each language's own
type system, because the difference is not observable in the emitted code:

* Java `byte`/`short`/`int` and platform-sized native spellings (`long`,
  `NSInteger`, Swift `Int`) are **refused**. Widening them would erase their
  source overflow or platform-width behavior. Java `long`, C++
  `std::int64_t`, Objective-C `long long` on the pinned Apple tuple, and Swift
  `Int64` are the accepted signed-integer spellings for the exact-eight pack.
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

The exact-eight C++/Objective-C/Swift/Java route policy is narrower than the
shared analyzer type inventory: it rejects every `string` function, parameter,
return, and literal. Swift uses Unicode canonical-equivalence equality, Java
uses UTF-16 code-unit equality, and C++ uses byte equality, so no single value
contract is sound without an enforced encoding/normalization boundary.
Integer arithmetic in those eight routes is conditional on the SMT-bound
`canonical-finite-no-error-input-domain`; wraparound, undefined overflow, traps,
non-finite values, and invalid division outside that domain are blocked rather
than called equivalent.

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
are untouched. Fixed-width native targets hold the canonical range in their
declared type, while emitted arithmetic helpers make overflow and invalid
division explicit under the canonical IR contract.

Execution is exact-toolchain bound: Java 21.0.11, Python 3.12.12, .NET SDK
10.0.301 / Roslyn 5.6.0, and TypeScript 5.9.2 on Node 26.0.0. A missing or
different source or target toolchain blocks the route instead of accepting
language-level compatibility flags as equivalent evidence.

The exact-eight native evidence is pinned to Xcode 26.6 build 17F113, macOS SDK
26.5, Apple clang 21.0.0, Swift 6.3.3, Darwin/arm64, and the recorded compiler
binary digests. Environment variables may repeat those repository pins for CI
clarity, but may not replace them with host-local values:

```bash
export ELMOS_CLANG_VERSION="$(clang --version | head -1)"
export ELMOS_SWIFT_VERSION="$(swiftc --version | head -1)"
```

A mismatched declared pin, SDK, platform, executable digest, or compiler
version is a hard block. An unset environment variable uses the immutable
repository pin; "whatever is installed" is never accepted as equivalent
evidence.

## Formal arithmetic evidence boundary

`tools/prove_arithmetic_compensation.py` keeps solver inputs and exact replay
commands for the integer compensation campaign. `PROVED` is reserved for an
unconditional 64-bit theorem over the recorded helper transcription.
`PROVED_UNDER_ASSUMPTIONS` is a separate, non-certifying state and is never
included in `counts.PROVED` or `all_required_proved`.

The TypeScript obligations are guard abstractions. Their bitvector model
reuses the canonical error/value and therefore does **not** model IEEE-754
binary64 rounding or special values, `Number.isSafeInteger`, `Math.trunc`, the
JavaScript remainder primitive, or the real emitted expression/helper
transcription. An UNSAT result for those five obligations is consequently
`PROVED_UNDER_ASSUMPTIONS`, with every missing bridge listed in the campaign
record. It is not an original-source, TypeScript-runtime, or helper theorem.

`--require-64-bit` requires unconditional proof for theorem obligations and
fails on both `BOUNDED` and `PROVED_UNDER_ASSUMPTIONS`. Callers may also select
the conditional state explicitly with
`--fail-on proved_under_assumptions,unknown,timeout,counterexample`.

For routed migrations the persisted `formal-input.json` content-addresses the
source and emitted-target bytes, both normalized IR objects, engine/emitter and
analyzer identities, solver options, environment, and assumptions. The SMT2,
result, and composition artifacts link back to its digest. The theorem scope
is only canonical normalized source IR to independently re-lifted target IR;
source/compiler/runtime soundness remains an assumption or `NOT_RUN`, and the
result remains `NOT_CERTIFIED`.

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

The command never follows symbolic links, verifies that every accepted file
stays stable while read, and enforces small/medium repository limits (at most
5,000 recognized source files, 64 MiB aggregate and 2 MiB per file). Known
build/vendor-directory entries are content-addressed exclusions with a
blocking `NOT_RUN` obligation; they cannot silently disappear from a complete
repository claim. Its content-addressed output contains one
`DISCOVERY_REQUIRED` work unit per source file. Discovery partitions multiple
eligible functions into stable child work units; each child keeps execution at
`NOT_RUN` until an independent behavior-case corpus is supplied. Framework,
database, I/O, concurrency, exceptions, async, object-graph and unresolved
cross-file semantics remain explicit blockers.

`discover` classifies every work unit with a precise verdict (`READY`,
`UNSUPPORTED`, `NO_CANDIDATE_DECLARATION`, `UNREADABLE`) using the same
compiler-backed analyzer the migration itself uses -- a candidate name is
proposed cheaply but never accepted without that analyzer's confirmation.
`batch` then attempts only `READY` units that also have a matching
`{unit_id}.json` behavior-case file under `--cases-directory`. The
`batch-checkpoint.jsonl` resumes explicit non-success skips only. A prior
`PASSED` record is not a trust anchor and is re-executed against source and
target behavior on every run. A partial run is never rounded up to `COMPLETE`.

## Whole-project assembly

A batch run proves each work unit in isolation. Every `PASSED` unit reuses the
same fixed emitted file name (`Migrated.java` / `Migrated.cs` / `migrated.py` /
`migrated.ts`, and for Java/C# the same class name too), so combining two units
verbatim would collide on the first duplicate -- a batch report by itself is
not a project anyone can build. Assembly is therefore consumed inside
`repository-pipeline`, in the same execution that produced the batch. The
standalone `assemble` CLI fails closed because an arbitrary JSON report on disk
cannot prove that behavior execution occurred.

For every `PASSED` unit it requires and re-verifies both target and route-evidence
SHA-256 digests, closes source/target observation counts, and recomputes batch
status counters before reading the output. It then places the unit's already-emitted source under a per-unit
namespace/module so nothing collides. It writes a real target build manifest:
Maven, .NET, Python, TypeScript, Go modules, Cargo, CMake (C++/Objective-C), or
SwiftPM. `FAILED` and `SKIPPED_*` units are recorded, with their reason, in
`assembly-manifest.json` under `excluded_units`; they are never silently
dropped and never included in the assembled project.

The repository pipeline's assembly verifier runs a real
whole-project compile/build check with the same exact-toolchain contract the
per-unit harness already enforces (`javac` across all sources, `python -m
compileall`, `dotnet build`, `tsc`, `go test ./...`, `cargo check --offline`,
CMake with the exact C++/Objective-C compiler, or `swift build`), and only on success writes local-run
and cloud-publishing guidance (`docs/LOCAL_RUN.md`, `docs/CLOUD_PUBLISHING.md`,
`deploy/deployment-options.json`) into the assembled project. The assembled
artifact is a locally verified, non-certified library of bounded pure
functions, not a running service. The guidance therefore documents a real
build and an explicitly reviewed package-publishing workflow; it does not
pretend one registry natively covers all nine target ecosystems.

Managed targets retain per-unit namespaces/modules. C++ and Objective-C units
are deliberately linked into one target so duplicate global symbols fail the
whole-project link instead of being hidden in separately compiled libraries.
Assembly does not invent a combined semantic API.
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
drift, resumes only explicit non-success skips, replays every prior successful
unit, rebuilds assembly from verified
bytes, and emits `repository-migration-artifact.zip` with an exact file/digest
manifest. It also builds a content-addressed `project-graph.json`, binds every
planned source path and digest to that graph, rebuilds it after target assembly
to detect mid-run drift, and records every unresolved classification, import,
dependency, resource, test, or semantic-index obligation.

`COMPLETE / PASSED_LOCAL` requires both every work unit to pass and the project
graph to have zero blocking obligations. Missing behavior cases, uncovered
symbols, unsupported units, unclassified files, unavailable compiler indexes,
unresolved dependencies, or execution failures produce `PARTIAL / LIMITED` and
remain visible in the report and artifact. Local execution never changes
independent or external evidence from `NOT_RUN`, and the 72-direction local
experiment never changes any governed route to certified.

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
