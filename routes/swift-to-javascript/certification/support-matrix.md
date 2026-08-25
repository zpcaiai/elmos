# Support matrix: swift-to-javascript

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:c9e37c444722f40fb92b0ea684adc46db6dcda50b5fa29a8c2c195fca129d43a`
- Source bytes: `3559`

## typed-pure-function-v1

- Status: `conditional`
- Strategy: `compiler-backed-semantic-ir`
- Evidence: `certification/local-development-evidence.json`, `certification/local-holdout-evidence.json`, `certification/local-representative-evidence.json`
- Reason: Conditionally supported for the route's explicitly declared exact JSDoc/target types inside the Node.js ES2022 ESM safe-integer/finite no-effect domain. Native analysis, concrete chunks, target compilation, behavior replay, and module composition must all pass; async, I/O, imports, dynamic evaluation, independent verification, and external certification remain blocked or NOT\_RUN.

## primitive-types

- Status: `conditional`
- Strategy: `exact-type-mapping`
- Evidence: `mappings/types.json`
- Reason: Integer is restricted to Number.isSafeInteger-compatible values; number is restricted to finite binary64 and boolean is exact. Cross-language string semantics are blocked pending a separate Unicode/code-unit corpus.

## nodejs-es2022-esm-safe-integer-finite-v1

- Status: `conditional`
- Strategy: `exact-jsdoc-types-and-runtime-domain-guards`
- Evidence: `lowering/profile.json`, `certification/local-development-evidence.json`, `certification/local-holdout-evidence.json`, `certification/local-representative-evidence.json`
- Reason: Integer values must satisfy Number.isSafeInteger, number values must be finite binary64, modules are ESM, and all effects are absent.

## string-semantics

- Status: `blocked`
- Strategy: `separate-unicode-code-unit-contract-required`
- Evidence: `certification/local-negative-evidence.json`
- Reason: The Node analyzer can represent strict equality and concatenation, but cross-runtime Unicode/code-unit equivalence is not claimed by this route.

## number-arithmetic

- Status: `blocked`
- Strategy: `separate-floating-point-arithmetic-contract-required`
- Evidence: None
- Reason: Finite inputs can still produce non-finite results and rounding differences; the Node exact route profile currently permits transport/comparison only.

## if-return-control-flow

- Status: `conditional`
- Strategy: `typed-structured-lowering`
- Evidence: `lowering/profile.json`
- Reason: If and return statements remain conditional on exact JSDoc types, the ESM closure, concrete spans, and successful native replay for this direction.

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
