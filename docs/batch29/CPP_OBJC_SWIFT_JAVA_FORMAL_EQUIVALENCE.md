# C++ / Objective-C / Swift / Java exact eight-route equivalence contract

## Scope

This contract adds the specialised formal-equivalence profile to exactly these
independent directed routes:

1. `cpp-to-objc`
2. `objc-to-cpp`
3. `cpp-to-swift`
4. `swift-to-cpp`
5. `objc-to-swift`
6. `swift-to-objc`
7. `cpp-to-java`
8. `java-to-cpp`

It does not grant this profile to a four-language Cartesian product. The wider
repository orchestration inventory may contain all ordered pairs of the nine
engine languages, including Java-to-Objective-C and Java-to-Swift, but those
route records do not inherit this exact-eight module proof or its evidence.
Every direction keeps separate source lifting, target lowering, runtime, proof,
negative, holdout, representative, independent and certification states.

The local maturity ceiling is `limited` / `NOT_CERTIFIED`. A local `UNSAT`
result may establish `PROVED_UNDER_ASSUMPTIONS` only for the recorded canonical
IR terms. It is not a theorem about arbitrary source text, a compiler, an
operating system, Foundation, the Objective-C runtime, or a customer program.

## Exact execution tuple

The native route evidence is valid only for the recorded tuple:

- macOS arm64;
- Xcode 26.6 build 17F113 and macOS SDK 26.5;
- Apple clang/clang++ 21.0.0, C++20;
- Objective-C with ARC and Foundation;
- Apple Swift 6.3.3 with canonical `integer` spelled `Int64`;
- Java/Javac 21.0.11 with canonical `integer` spelled `long`;
- Z3 4.16.0 with fixed options, timeout, and random seed.

An unpinned or mismatched toolchain blocks execution. Other platforms and
toolchains remain `NOT_RUN` until replayed as their own exact environment.

## Semantic profiles

### `typed-pure-function-v1`

The supported core is a named, statically typed, side-effect-free function
using only:

- exact primitive parameters and return values (`integer`, finite `number`,
  and `boolean` only);
- literals and parameter references;
- the allowlisted typed binary operators;
- structured `if` and `return`.

Canonical `integer` means signed 64-bit. This profile accepts Java `long`, C++
`std::int64_t`, Objective-C `long long` on the pinned Apple tuple, and Swift
`Int64`. Integer arithmetic is supported only on the machine-checked
`canonical-finite-no-error-input-domain`: no accepted input may overflow or use an
invalid divisor in the canonical denotation. The SMT query contains this
precondition and first proves it satisfiable; native runtime cases must also be
inside it. Java wraparound, C++/Objective-C undefined overflow, Swift traps,
and all other out-of-domain arithmetic behavior are explicitly blocked rather
than declared equivalent. Narrow integers, unsigned integers, C++ `long`, Objective-C
`NSInteger`, Swift `Int`, nullable/boxed values, reference identity, pointer
arithmetic, raw memory, templates/generics, dynamic dispatch, exceptions,
I/O, concurrency, reflection, and framework state fail closed.

`string` is also blocked for all eight specialized routes. Swift equality uses
Unicode canonical equivalence, Java compares UTF-16 code units, C++ compares
bytes, and Objective-C adds a Foundation representation boundary. A future
string profile must pin encoding and normalization at every call boundary;
the current proof never collapses those semantics into a false common type.

Canonical `number` is limited to finite IEEE-754 binary64 transport, return,
comparison, and branch observations, including the sign bit of zero. Number
`+`, `-`, `*`, `/`, and `%` are blocked: finite inputs may produce non-finite
results and the required rounding/payload contract is not yet evidenced.
Non-finite literals, arguments, expected values, and results fail closed. A
route cannot silently replace an error, trap, signal, or thrown exception with
a returned value.

### `typed-pure-module-v1`

This module profile is a conservative composition over at least three
independently proved functions; the current fixture contains five and covers
integer, finite-number, and boolean semantics. Its manifest must match the source and target
symbol sets exactly, including parameter names/order/types and return types.
Every function needs non-empty independent cases and all four local layers.

The composition rule applies only when the module has no inter-function calls,
global or static mutable state, aliasing, heap effects, I/O, concurrency, or
unmodelled exceptions. One missing function, signature drift, missing case,
unmapped syntax chunk, failed runtime observation, solver unknown/timeout, or
counterexample blocks the whole module composition. It is not valid to infer a
module theorem by averaging function results.

## Required equivalence layers

1. **Native lifting and target re-lifting.** Clang AST, SwiftSyntax, and the JDK
   Compiler Tree API independently lift original source and emitted target.
   The target pass is not allowed to reuse source IR.
2. **Semantic equivalence.** Canonical symbol, signature, typed expression,
   branch, return, error, and numeric semantics must match exactly. Unknown or
   dropped nodes fail.
3. **Syntax/phrase/chunk equivalence.** Every function, parameter, statement,
   and expression has an RFC 6901 semantic path, canonical semantic hash, and
   concrete source and target UTF-8 byte span. Required chunks must map one to
   one with full coverage; missing, ambiguous, overlapping-invalid, or
   hash-mismatched chunks fail.
4. **Behavior equivalence.** The original source, canonical evaluator, and
   compiled target run independently for development, holdout, representative,
   and bounded module cases. Returned observations are typed and content
   addressed; binary64 values use exact bits. Rejected source spellings,
   undeclared routes, missing symbols, and tampered helpers are executed as
   separate fail-closed negative cases. Native equivalence of source-language
   traps, undefined behavior, and thrown-error categories is not inferred from
   these returned-value runs and remains outside the passing local scope.
5. **Formal equivalence.** Z3 receives independently encoded source-normalized
   and target-re-lifted denotations plus explicit input alignment. A passing
   local result requires satisfiable assumptions and an `UNSAT` divergence
   query. SMT2, result, assumptions, helper digests, formal input, and replay
   command are byte-bound. Each module function independently binds a formal
   input JSON, SMT2 file, solver-result JSON, assumptions, and a replay that
   must reproduce `UNSAT`.

All five layers are conjunctive for the declared bounded, return-value corpus.
The canonical IR theorem includes explicit arithmetic error terms, but it is
not promoted to an original-source runtime theorem. `AXIOM`, `BOUNDED`,
`UNKNOWN`, `TIMEOUT`, `NOT_RUN`, `VACUOUS`, or `COUNTEREXAMPLE` never pass the
formal layer.

## Helper and analyzer integrity

Emitted checked-arithmetic and non-zero helpers are part of the proof input.
Target re-lifting may recognize a helper only when its exact language, name,
arity, normalized body, and digest match the emitter contract. A renamed,
partially copied, reordered-with-changed-semantics, or tampered helper blocks
the route. Helper recognition is never a permissive "unknown call equals
canonical operator" rule.

Source/target artifact bytes, analyzers, emitter, module composer, solver,
toolchain identity, semantic profile, cases, and all produced evidence are
content addressed. Generated binaries and caches are rebuildable and are not
substitutes for source evidence.

## Evidence and gate boundary

Each route carries three independent positive corpora, language-specific
negative cases, persisted native artifacts, normalized source/target IR,
source spans, chunk map, behavior comparison, solver input/result, module
composition, and packed replay. The exact eight-route Batch 35 pack is separate
from the immutable six-language complete 30-route pack.

Local structural and runtime gates can report only local engineering status.
Independent verifier, customer representative repository, other OS/arch,
production, compiler/runtime soundness, and external certification evidence
remain `NOT_RUN` until those exact executions occur under authorization.
