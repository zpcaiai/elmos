# Support matrix: cpp-to-java

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:250f5857b9bacd1b4767c32dc5b50af17e643e73a21e393d93924febc4390f27`
- Source bytes: `4131`

## typed-pure-function-v1

- Status: `conditional`
- Strategy: `compiler-backed-semantic-ir`
- Evidence: `certification/local-development-evidence.json`, `certification/local-holdout-evidence.json`, `certification/local-representative-evidence.json`
- Reason: Conditionally supported only for integer, finite-number, and boolean functions inside the canonical finite no-error input domain; string semantics and arithmetic-error outcomes are blocked. Native analysis, target compilation, separate typed corpora, and behavior replay must each pass before local execution may be raised; independent/external verification remain NOT\_RUN.

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
