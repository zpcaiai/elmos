# Batch 29 directed route matrix

`routes/inventory.json` is authoritative. Batch 29 preserves the legacy 30 and
specialized 8 provenance sets, then adds one explicit 34-route completion set.
Their union is the governed nine-language matrix; engine support alone never
creates a passing route claim.

## Evidence boundary

- Engine languages: 9 (`java`, `csharp`, `go`, `rust`, `python`,
  `typescript`, `cpp`, `objc`, `swift`).
- Governed directed routes: 72 = legacy 30 + specialized 8 + completion 34.
- Matrix expansion is exact and explicit: 9 × 8, with no self routes.
- Local maturity ceiling: `limited`.
- Current local execution: all 72 routes are `NOT_RUN`. Thirty-eight routes
  retain historical local artifacts, but their captured engine-source bytes no
  longer match the live engine snapshot; inventory generation invalidates those
  results instead of advertising stale `PASSED_LOCAL` evidence. The 34 completion
  routes have not run.
- Repository execution: all 72 governed routes are `NOT_RUN`.
- Independent verification and external/customer certification: `NOT_RUN`.
- Certification decision: `NOT_CERTIFIED` for every route.

Inventory summary: 72 `limited`, 0 `certified`; current execution contains 0
`PASSED_LOCAL` routes.
A fresh route replay may record `PASSED_LOCAL` only while its captured engine
source bundle still matches the live bytes; it never raises certification.

- Independent verification: `NOT_RUN`.
- External certification: `NOT_RUN`.

Local compiler/runtime, behavior, span, and solver execution is engineering
evidence only for its exact bounded profile and recorded toolchain tuple.

## Legacy complete 30

The original six-language policy remains the complete directed permutation
over `java`, `csharp`, `go`, `rust`, `python`, and `typescript`.

| Source | Five independent targets |
| --- | --- |
| Java | `java-to-csharp`, `java-to-go`, `java-to-rust`, `java-to-python`, `java-to-typescript` |
| C# | `csharp-to-java`, `csharp-to-go`, `csharp-to-rust`, `csharp-to-python`, `csharp-to-typescript` |
| Go | `go-to-java`, `go-to-csharp`, `go-to-rust`, `go-to-python`, `go-to-typescript` |
| Rust | `rust-to-java`, `rust-to-csharp`, `rust-to-go`, `rust-to-python`, `rust-to-typescript` |
| Python | `python-to-java`, `python-to-csharp`, `python-to-go`, `python-to-rust`, `python-to-typescript` |
| TypeScript | `typescript-to-java`, `typescript-to-csharp`, `typescript-to-go`, `typescript-to-rust`, `typescript-to-python` |

The old exact-30 pack and its evidence remain immutable; specialized replay
does not regenerate them.

## Specialized exact 8

| Route | Local profile |
| --- | --- |
| `cpp-to-objc` | function + five-function module |
| `objc-to-cpp` | function + five-function module |
| `cpp-to-swift` | function + five-function module |
| `swift-to-cpp` | function + five-function module |
| `objc-to-swift` | function + five-function module |
| `swift-to-objc` | function + five-function module |
| `cpp-to-java` | function + five-function module |
| `java-to-cpp` | function + five-function module |

These routes require concrete UTF-8 source/target spans and the exact Apple
tuple: C++20, `Apple clang version 21.0.0 (clang-2100.1.1.101)`, and
`arm64-apple-darwin25.6.0`. Their local type evidence is split across three
independent corpora: integer, finite binary64 transport (including negative
zero), and boolean branch/logic. String and number arithmetic are blocked.
Integer arithmetic is conditional on
`canonical-finite-no-error-input-domain`; out-of-domain behavior is not
claimed equivalent.

The module contract requires at least three functions covering integer,
finite-number, and boolean semantics. `cpp-to-java` retains a historical local
function/module run, but source drift has invalidated it for current admission;
all eight specialized routes therefore remain `NOT_RUN` in the live inventory.
Scaffolds, old artifacts, and contracts are not current execution evidence.
Compiler/runtime soundness and external verification remain `NOT_RUN`.

## Nine-language completion 34

These exact additions close the route-directory and admission matrix without
claiming execution. They use the bounded function profile and start at
`limited / NOT_RUN / NOT_CERTIFIED`.

| Source | Additional targets |
| --- | --- |
| Java | `java-to-objc`, `java-to-swift` |
| C# | `csharp-to-cpp`, `csharp-to-objc`, `csharp-to-swift` |
| Go | `go-to-cpp`, `go-to-objc`, `go-to-swift` |
| Rust | `rust-to-cpp`, `rust-to-objc`, `rust-to-swift` |
| Python | `python-to-cpp`, `python-to-objc`, `python-to-swift` |
| TypeScript | `typescript-to-cpp`, `typescript-to-objc`, `typescript-to-swift` |
| C++ | `cpp-to-csharp`, `cpp-to-go`, `cpp-to-rust`, `cpp-to-python`, `cpp-to-typescript` |
| Objective-C | `objc-to-java`, `objc-to-csharp`, `objc-to-go`, `objc-to-rust`, `objc-to-python`, `objc-to-typescript` |
| Swift | `swift-to-java`, `swift-to-csharp`, `swift-to-go`, `swift-to-rust`, `swift-to-python`, `swift-to-typescript` |

## Repository experiment boundary

The local engine can attempt all 72 governed directions under the bounded
`typed-pure-function-v1` repository execution mode and real target build tools.
Route-pack completeness is still not a general repository-semantics claim.
Project-graph completeness, every
source symbol, excluded input, resource, dependency, configuration, and test
obligation must close before a repository can report `COMPLETE`; otherwise it
remains `PARTIAL / LIMITED`. No checked-in SMALL/MEDIUM repository campaign has
raised any route's repository execution status above `NOT_RUN`.

## Exact replay

Replay one declared route without touching the other 71:

```bash
python3 scripts/batch29/run_polyglot_routes.py --repo-root . \
  --route cpp-to-java
```

Replay only the specialized set (never the old 30):

```bash
python3 scripts/batch29/run_polyglot_routes.py --repo-root . \
  --route-set cpp-objc-swift-java-exact-8
```

The entry point resolves the pinned `uv` binary and creates a new locked
temporary project environment on every authoritative runner, validator, and
gate invocation; the mutable project `.venv` is never the proof-runtime trust
root. Both commands run the route validator and conservative gate. A passing
local replay still reports `limited / NOT_CERTIFIED`.

Prepare or replay only the 34 completion routes:

```bash
python3 scripts/batch29/run_polyglot_routes.py --repo-root . \
  --prepare-route-set nine-language-completion-34
```

The repository wrapper `make -f Makefile.batch29 b29-nine-language-prepare`
creates deterministic NOT_RUN scaffolds and validates the matrix. Target
`b29-nine-language-replay` performs an explicit all-72 local replay. Neither
target changes independent or certification evidence.

After all eight route validators and gates pass from one final source snapshot,
build the separate exact-eight Batch 35 pack without regenerating the immutable
legacy exact-30 pack:

```bash
make -f Makefile.batch29 b29-specialized-formal-pack
```

The pack generator copies the existing arithmetic residual campaign only as
background solver evidence. Exact-eight function and five-function module
claims are derived from the eight route-local byte closures and remain
assumption-bound and `NOT_CERTIFIED`.
