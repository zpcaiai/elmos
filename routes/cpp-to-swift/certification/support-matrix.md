# Support matrix: cpp-to-swift

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:08056cac23c7fa773f83c6cdde8f7b52a4c7d2ece37690875178eb31d43077af`
- Source bytes: `5130`

## typed-pure-function-v1

- Status: `certified`
- Strategy: `compiler-backed-semantic-ir`
- Evidence: `certification/evidence.json`
- Reason: Certified for typed pure function semantic conversion under the verified typed-pure-function-v1 profile.

## primitive-types

- Status: `conditional`
- Strategy: `exact-type-mapping`
- Evidence: `mappings/types.json`
- Reason: Integer, finite IEEE-754 binary64 number, and boolean are mapped explicitly only inside the canonical finite no-error input domain. String is not in the specialized profile.

## canonical-finite-no-error-input-domain

- Status: `supported`
- Strategy: `explicit-domain-precondition`
- Evidence: `lowering/profile.json`, `certification/local-development-evidence.json`, `certification/local-holdout-evidence.json`, `certification/local-representative-evidence.json`
- Reason: All three local type corpora and formal obligations are scoped to inputs for which source and target arithmetic error flags are both zero.

## string-semantics

- Status: `blocked`
- Strategy: `dedicated-string-contract-required`
- Evidence: `certification/local-negative-evidence.json`
- Reason: Unicode normalization, code-unit encoding, and equality contracts differ; the specialized exact routes reject string before artifact production.

## arithmetic-error-domain

- Status: `blocked`
- Strategy: `separate-error-semantics-profile-required`
- Evidence: None
- Reason: Java wrap, C++ undefined behavior, and Swift traps are not claimed equivalent; out-of-domain arithmetic-error inputs remain BLOCKED/NOT\_SUPPORTED.

## finite-number-transport-comparison

- Status: `conditional`
- Strategy: `fp64-bit-exact-native-replay`
- Evidence: `certification/local-holdout-evidence.json`
- Reason: Finite binary64 parameters may be transported, returned, branched on, and compared; the holdout contract requires negative zero and finite boundary values.

## number-arithmetic

- Status: `blocked`
- Strategy: `dedicated-fp-arithmetic-contract-required`
- Evidence: None
- Reason: Number +, -, \*, /, and % remain outside the exact-eight profile because finite inputs can produce infinities/NaNs and rounding/payload behavior is unproved.

## if-return-control-flow

- Status: `supported`
- Strategy: `typed-structured-lowering`
- Evidence: `lowering/profile.json`
- Reason: If and return statements are lowered from compiler-backed syntax trees.

## framework-database-async-concurrency

- Status: `blocked`
- Strategy: `separate-exact-pack`
- Evidence: None
- Reason: Requires exact Batch 30/31 packs and independent runtime evidence; it is not hidden in this route.

## typed-pure-module-v1

- Status: `conditional`
- Strategy: `per-function-proof-plus-module-composition`
- Evidence: `certification/module-equivalence.json`
- Reason: Requires at least three independently observed functions, exact symbol/signature closure, semantic chunks, behavior replay, and module composition evidence.

## object-graph-lifecycle

- Status: `blocked`
- Strategy: `separate-exact-pack`
- Evidence: None
- Reason: Object graph lifecycle, finalizers, references and circular graph semantics require specialized lifecycle runtime packs and are fail-closed blocked under typed-pure-function-v1.

## async-concurrency

- Status: `blocked`
- Strategy: `separate-exact-pack`
- Evidence: None
- Reason: Asynchronous coroutines, thread scheduling, locks and concurrency primitives require dedicated concurrent runtime packs and are fail-closed blocked under typed-pure-function-v1.

## exception-unwinding

- Status: `blocked`
- Strategy: `separate-exact-pack`
- Evidence: None
- Reason: Cross-language stack exception unwinding, landing pads and runtime throw/catch unwinding semantics require specialized exception runtime packs and are fail-closed blocked under typed-pure-function-v1.

## complex-framework-and-ui

- Status: `blocked`
- Strategy: `separate-exact-pack`
- Evidence: None
- Reason: Complex framework lifecycle, dependency injection, and UI widget hierarchy conversions require dedicated framework modernization packs and are fail-closed blocked under typed-pure-function-v1.
