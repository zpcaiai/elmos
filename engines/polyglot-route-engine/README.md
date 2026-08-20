# ELMOS Polyglot Route Engine

This engine implements a compiler-backed, fail-closed vertical slice across Java,
Python, C#, TypeScript, Go, Rust, C++, Objective-C, Swift and PHP. Every attempted
direction is evaluated independently; no reverse or Cartesian route is inferred.

All eleven have source inventory, candidate discovery and target-project
assembly plumbing. The repository capability inventory explicitly lists all 110
ordered language pairs; it never infers an unlisted direction and a route record is not
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

| Canonical | java | python | csharp | typescript | go | rust | cpp | objc | swift | php |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `integer` | `long` | `int` | `long` | guarded `number` | `int64` | `i64` | `std::int64_t` | `long long` | `Int64` | `int` |
| `number` | `double` | `float` | `double` | `number` | `float64` | `f64` | `double` | `double` | `Double` | `float` |
| `boolean` | `boolean` | `bool` | `bool` | `boolean` | `bool` | `bool` | `bool` | `BOOL` | `Bool` | `bool` |
| `string` | `String` | `str` | `string` | `string` | `string` | `String` | `std::string` | `NSString *` | `String` | `string` |

PHP's `int` is platform-width rather than fixed at 64 bits, so it is admitted
only on a build whose `PHP_INT_SIZE` the toolchain probe has observed to be 8;
a 32-bit build is refused with `EXACT_TOOLCHAIN_PHP_INT_WIDTH_UNSUPPORTED`
rather than silently reinterpreting every `integer` at the wrong width.

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
only when a function actually carries an `integer`. TypeScript `number`
arithmetic and number-return boundaries are independently wrapped with the
exact `_elmosRequireFiniteNumber` helper, so NaN or infinity at any nested
arithmetic node fails before it can be hidden by a later branch or comparison.
Fixed-width native targets hold the canonical range in their declared type,
while emitted arithmetic helpers make overflow and invalid division explicit
under the canonical IR contract.

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


## PHP

PHP is the one target in the matrix whose integer does not fail loudly on
overflow and does not wrap either: `PHP_INT_MAX + 1` silently becomes a
`float`. That promotion is exact -- `int op int` is an `int` unless the
mathematical result left the 64-bit range -- so it is not a hazard to be
worked around but the signal R1 is built on. Each of `elmos_checked_add`,
`_sub` and `_mul` performs the operation and then asks `is_int` of the result,
which is a sound check rather than a heuristic.

R2 splits. `intdiv` already throws `DivisionByZeroError` on a zero divisor and
`ArithmeticError` on `PHP_INT_MIN / -1`, so the division helper only re-labels
those with the canonical messages. `%` throws on a zero divisor but answers
**0** for `PHP_INT_MIN % -1` rather than failing, so that arm is a real guard.

Four more places where the obvious emission would be wrong, all reproduced
against a real interpreter before the corresponding arm was written, and
re-checkable at any time with `php tools/verify_php_semantics.php`, which
restates all 44 of them as executable assertions naming the arm each one
supports (44/44 on 8.4.21 and on the pinned 8.5.9):

* `/` on two integers is **not** truncating division. `7 / 2` is `3.5`, and the
  result is not even an `int`. Integer division is `intdiv`.
* `%` is an **integer** operator that casts float operands to int, so `7.5 % 2`
  is `1`. The float remainder is `fmod`, which truncates and matches Java, C#
  and TypeScript exactly.
* `==` type-juggles. `'1' == '01'` and `'10' == '1e1'` are both true. The
  canonical value comparison is `===` -- which also compares types, so
  `1 === 1.0` is false, and the one mixed case the lattice admits
  (integer against number) has the integer side widened explicitly first.
* A double-quoted string interpolates `$name` and does not understand JSON's
  `\uXXXX`. Emitted string literals are single-quoted, where the only two
  escapes are `\\` and `\'`.

`+` on two strings is a `TypeError` in PHP 8, so string concatenation emits `.`.
A bare `-9223372036854775808` is a float, so the minimum integer literal emits
`PHP_INT_MIN`. Function names resolve case-insensitively while variables do
not, so the identifier policy folds case for the function role only.

### One namespace per assembled unit

Every other target is isolated by where its file lands: a Go package, a Rust
module, a C++ translation unit, a Java package. PHP gets nothing from directory
placement, because a `function` at file scope is unconditionally global. Two
assembled units that both need `elmos_checked_add` are therefore a fatal
"Cannot redeclare function" the moment Composer autoloads the second -- which
is to say a repository-level PHP assembly with two units and any integer
arithmetic would not load at all.

`assembly._place_php` gives each unit its own `namespace Elmos\Generated\<Unit>;`,
the same division of labour Java and C# already use, where the emitted file
carries no package and the placer adds the one that matches where the file
lands. The namespace goes *after* `declare(strict_types=1);`, which must stay
the first statement.

That relocation has one consequence worth stating on its own, because it fails
only on the path the guards exist for. Inside a namespace PHP falls back to the
global namespace for an unqualified *function* or *constant*, but **not** for a
class: `new ArithmeticError` inside `namespace Elmos\Generated\Wu00001`
resolves to `Elmos\Generated\Wu00001\ArithmeticError` and dies with "Class not
found". Every class reference in the emitted helpers is therefore written fully
qualified, `\ArithmeticError` and `\DivisionByZeroError`, so the R1/R2 guards
raise the canonical error rather than a class-resolution error.

### The PHP frontend

`native/php/analyzer.php` lifts source PHP through `token_get_all()` --
`ext/tokenizer` is a thin wrapper over the Zend scanner itself, so the token
stream is the compiler's own lexical analysis rather than a re-lex. PHP ships
no first-party tree comparable to the JDK Compiler Tree API or clang's AST
dump: `ext/ast` exposes the real Zend AST but is a PECL extension, and
nikic/PHP-Parser is a faithful but independent reimplementation in userland.

Three layers therefore have to agree before an IR is produced. `php -l` -- the
real compiler -- accepts the file. The lift asserts that concatenating every
token reproduces the source byte-for-byte, which is what makes the byte spans
it reports incapable of drifting from the file the caller hashed. And when the
`ast` extension happens to be loaded, the lifted shape is compared against
Zend's own AST and any disagreement is fatal. That third layer can only ever
*refuse* a route, so an analysis is no weaker on a host without the extension,
but it is better witnessed on a host with it. A mutation campaign against the
lift confirms it is load-bearing rather than decorative: seeding a wrong
canonical type for any of the four parameter spellings, a dropped trailing
statement, a renamed subject, or a reordered parameter list all survive the lift
and are all refused by the witness.

Two details of that layer are deliberate. The AST version is pinned rather than
"newest supported", because the node shapes the comparison reads are
version-dependent; an extension that is loaded but cannot supply the pinned
version is a configuration error and fails closed, while an absent extension is
the documented weaker mode. And the witness only fires when `ast` is compiled
into the pinned build: the engine invokes PHP with `-n`, which drops every
php.ini, so a PECL install activated through an ini file is invisible on
purpose -- an analysis result must not depend on configuration the toolchain
pin does not cover.

The subset the frontend admits is narrower than the language in ways worth
stating, because each refusal is a place where a plausible lift would have been
wrong rather than merely unsupported: a missing `declare(strict_types=1)`
(without it the emitted types are coercive), `==`/`!=` (type juggling), `and`/
`or` (a precedence no other target has), a raw `/` on two integers, a raw `%`
with a float operand, a non-decimal integer literal, an integer literal outside
the 64-bit range (PHP's lexer has already turned it into a float), string
interpolation, and every by-reference, variadic, nullable, union or defaulted
parameter.

### Toolchain pinning

`toolchains._php` pins the install the way Go's is pinned -- whole-tree
manifest, executable file record, before/after sandwich around the one
subprocess -- plus a runtime identity document, because two PHP builds that
report the same `php --version` can still disagree semantically. The document
covers `PHP_INT_SIZE`, the float model, the ini settings that change an
observed value rather than a diagnostic, and the loaded extension set.

The digests are machine-specific. Run `tools/pin_php_toolchain.py` on the
pinning host and paste its output over the `_EXPECTED_PHP_*` block. Until they
are pinned the probe fails closed with `EXACT_TOOLCHAIN_PHP_NOT_PINNED` rather
than accepting whatever `php` is on PATH.

Two properties of the tree contract are PHP-specific and worth stating, because
in both cases the obvious rule is the wrong one.

The tree is **not** required to be symlink-free, unlike Go's and Rust's. That
contract fits an extracted tarball of plain files and fits nothing a package
manager laid down: a stock Homebrew PHP ships `bin/phar -> bin/phar.phar` and
`pecl -> /opt/homebrew/lib/php/pecl`, so a symlink-free rule refuses every
Homebrew PHP that will ever exist, and a rule no real install can satisfy is
not strict but unusable. Links are instead *recorded* as part of the pinned
identity, exactly as the Python probe already does, so repointing one is drift
even when no file's content changed. Links resolving outside the root are kept
in a separate map and named as unbound in the profile, because their content
genuinely is not covered and folding them in would imply otherwise. The one
thing still refused outright is an escaping link to a loadable object: anything
the interpreter could `dlopen` has to live inside the tree the pin binds.

And `ext/tokenizer` is pinned as either `builtin` or a path inside the root.
The engine runs PHP with `-n`, which drops every php.ini; on a build that ships
the tokenizer as a shared module activated through conf.d — Debian and Ubuntu
do — that removes `token_get_all` and the frontend cannot run at all. The
extension is re-added by absolute path from inside the pinned root, never by
bare name, so the object being loaded is the one the tree digest covers rather
than whatever sits on the extension search path. The probe cross-checks the
build against the pinned value and refuses a mismatch.

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
