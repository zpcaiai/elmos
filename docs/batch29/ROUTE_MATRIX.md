# Batch 29 directed route matrix

`routes/inventory.json` is authoritative. The active matrix is the exact
directed permutation of 13 language identities: `java`, `csharp`, `go`,
`rust`, `python`, `typescript`, `cpp`, `objc`, `swift`, `php`, `kotlin`,
`react`, and `flutter`. Batch 29 preserves the historical 30, 8, 34, 72, 90,
and 110 provenance sets without rewriting their identities. JavaScript remains
addressable only as deprecated historical evidence and is not an active source
or target. Engine support alone never creates a passing route claim.

The generated registry retains these exact set identities:
`legacy-complete-30`, `cpp-objc-swift-java-exact-8`,
`nine-language-completion-34`, `nine-language-complete-72`,
`javascript-node26-completion-18`, `ten-language-complete-90`,
`php-php85-completion-20`, `eleven-language-complete-110`,
`kotlin-react-flutter-completion-66`, and
`thirteen-language-complete-156`.

> ### Route-count provenance — read before quoting any denominator (K6)
>
> Verified 2026-08-24 against the generated inventory. `routes/inventory.json`
> is the only route-record authority.
>
> **Current surface: 156 directed routes across 13 active languages**
> (13 × 12, no self-routes).
>
> `/72`, `/90`, and `/110` survive only as retained provenance-set
> denominators. None describes the active surface. The 182-direction figure is
> the repository compatibility test matrix (13 active identities plus retained
> JavaScript machinery); it is not a governed route count.

## Evidence boundary

- Active engine languages: 13; deprecated engine compatibility languages: one
  (`javascript`).
- Governed directed routes: 156 = 90 active non-V3 directions plus the exact
  66 directions that have Kotlin, React, or Flutter on at least one side.
- Matrix expansion is exact and explicit: 13 × 12, with no self routes.
- Local maturity distribution: 90 `limited`, 66 `research`, 0 `certified`.
- Current local execution: all 156 routes are `NOT_RUN` by design. The exact
  split is `38` manifest-drift directions + `52` not-executed directions +
  `66` V3 research campaigns not replayed. Stale historical artifacts are invalidated
  against the live engine snapshot; no stale `PASSED_LOCAL` evidence is exported.
- Repository execution: all 156 governed routes are `NOT_RUN`.
- Independent verification and external/customer certification: `NOT_RUN`.
- Certification decision: `NOT_CERTIFIED` for every route.

Inventory summary: 90 `limited`, 66 `research`, 0 `certified`; current
execution contains 0 `PASSED_LOCAL` routes.
A fresh replay of an execution-admitted mutable route may record `PASSED_LOCAL`
only while its captured engine source bundle still matches the live bytes; it
never raises certification.

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

## Deprecated Node.js 26 completion 18

Node.js is an independent historical `javascript` identity, not a TypeScript
alias. These 18 keys and their filed evidence are retained under
`javascript-node26-completion-18`, but they are deprecated and excluded from
the active 156-route matrix. They cannot be selected by the active route
parser. Retention does not upgrade their `NOT_RUN / NOT_CERTIFIED` evidence.

| Source | Node.js-directed target(s) |
| --- | --- |
| Java | `java-to-javascript` |
| C# | `csharp-to-javascript` |
| Go | `go-to-javascript` |
| Rust | `rust-to-javascript` |
| Python | `python-to-javascript` |
| TypeScript | `typescript-to-javascript` |
| C++ | `cpp-to-javascript` |
| Objective-C | `objc-to-javascript` |
| Swift | `swift-to-javascript` |
| JavaScript | `javascript-to-java`, `javascript-to-csharp`, `javascript-to-go`, `javascript-to-rust`, `javascript-to-python`, `javascript-to-typescript`, `javascript-to-cpp`, `javascript-to-objc`, `javascript-to-swift` |

The common Node profile is
`nodejs-es2022-esm-safe-integer-finite-v1`: explicit canonical integers are
restricted to the JavaScript safe-integer subset, canonical numbers must be
finite binary64 values, booleans are exact, and domain violations fail closed
before target execution. Async/event-loop behavior, I/O, imports, dynamic
evaluation, reflection, shared state, and framework behavior are blocked.

`typescript-to-javascript` and `javascript-to-typescript` have a narrower
exception: TypeScript `number` is not relabelled as canonical `integer`.
Those two routes may cover only finite-number transport/comparison, boolean,
and the pinned ECMAScript strict string equality/concatenation subset. Their
integer semantics stay explicitly blocked, including when a JavaScript source
uses an `integer` JSDoc declaration.

## PHP and V3 completion

`php-php85-completion-20` retains the PHP 8.5 route expansion and its historical
JavaScript-facing keys. The active matrix uses PHP 8.5.9 only for active route
execution; the central synthesis profile separately retains PHP 8.4.12.

`kotlin-react-flutter-completion-66` is the exact set of active directions with
Kotlin, React, or Flutter on at least one side. Its local compiler/parser and
repository surfaces are engineering readiness only. Every one of the 66 route
records remains `research / NOT_RUN / NOT_CERTIFIED` until an approved,
route-specific campaign exists, that campaign is replayed, and independent
evidence exists. Flutter readiness is deliberately the
dependency-free, import-free pure-Dart subset: the exact Flutter-bundled Dart
SDK analyzes, compiles and executes a linked kernel. Widget/UI, engine bundle,
plugin, asset, platform, emulator and device behavior remains `NOT_RUN`.

## Repository experiment boundary

The local engine exposes analyzer, emitter, repository-assembly, and exact
target-build surfaces for all 13 active identities. The repository campaign
therefore enumerates all 156 directions, but the 66 V3 directions are not yet
admitted route packs: direct route execution fails closed until a bounded
semantic/target Profile and route-specific corpus are approved. Individual
repository-pipeline engineering probes do not upgrade those research records.
Route-pack completeness is still not a general repository-semantics claim.
Project-graph completeness, every
source symbol, excluded input, resource, dependency, configuration, and test
obligation must close before a repository can report `COMPLETE`; otherwise it
remains `PARTIAL / LIMITED`. No checked-in SMALL/MEDIUM repository campaign has
raised any route's repository execution status above `NOT_RUN`.

## Exact admitted replay and fail-closed boundaries

Replay one of the 60 execution-admitted mutable routes without touching the
other active routes:

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

The other 96 active routes are not direct replay selections. The immutable
legacy 30 fail closed with
`LEGACY_ROUTE_IMMUTABLE_REEXECUTION_REQUIRES_NEW_PACK_VERSION`; the 66 V3
research routes fail at direct CLI selection with
`V3_ROUTE_RESEARCH_NOT_EXECUTABLE`. The deeper mutation boundary independently
fails with `V3_ROUTE_RESEARCH_PACK_REQUIRES_CAMPAIGN` until an exact
route-specific campaign is approved.

Prepare only the 34 completion routes:

```bash
python3 scripts/batch29/run_polyglot_routes.py --repo-root . \
  --prepare-route-set nine-language-completion-34
```

The repository wrapper `make -f Makefile.batch29 b29-nine-language-prepare`
creates deterministic NOT_RUN scaffolds and validates the matrix. Target
`b29-nine-language-replay` verifies the immutable legacy 30 through their
read-only authority, then replays only the 42 mutable members of the preserved
nine-language complete 72. It is not a direct replay of all 72 routes. Neither
target changes independent or certification evidence.

The following historical targets retain deprecated JavaScript scaffolds for
evidence lookup only; they do not add those directions back to the active
matrix:

```bash
make -f Makefile.batch29 b29-nodejs-verify
make -f Makefile.batch29 b29-ten-language-verify
```

These commands only verify immutable pack structure and binding; they never
prepare, execute, or rewrite historical evidence. The active 156 can be
synchronized as research/NOT_RUN metadata with
`--prepare-route-set thirteen-language-complete-156`, but its V3 directions
remain research-only and therefore the full set is not an executable replay
selection. No set inherits execution or certification credit from another.

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
