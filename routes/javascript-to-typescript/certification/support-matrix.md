# Support matrix: javascript-to-typescript

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:c4033879c0aacd460cb2af80d2f1bc814ad19b2ed873ac731054e117068fccf4`
- Source bytes: `3638`

## typed-pure-function-v1

- Status: `conditional`
- Strategy: `compiler-backed-semantic-ir`
- Evidence: `certification/local-development-evidence.json`, `certification/local-holdout-evidence.json`, `certification/local-representative-evidence.json`
- Reason: Conditionally supported for the route's explicitly declared exact JSDoc/target types inside the Node.js ES2022 ESM safe-integer/finite no-effect domain. Native analysis, concrete chunks, target compilation, behavior replay, and module composition must all pass; async, I/O, imports, dynamic evaluation, independent verification, and external certification remain blocked or NOT\_RUN.

## primitive-types

- Status: `conditional`
- Strategy: `exact-type-mapping`
- Evidence: `mappings/types.json`
- Reason: TypeScript has no explicit canonical integer annotation in this profile; JavaScript/TypeScript is limited to finite binary64 transport/comparison, boolean, and strict ECMAScript string equality/concatenation. Integer is blocked.

## nodejs-es2022-esm-safe-integer-finite-v1

- Status: `conditional`
- Strategy: `exact-jsdoc-types-and-runtime-domain-guards`
- Evidence: `lowering/profile.json`, `certification/local-development-evidence.json`, `certification/local-holdout-evidence.json`, `certification/local-representative-evidence.json`
- Reason: Integer values must satisfy Number.isSafeInteger, number values must be finite binary64, modules are ESM, and all effects are absent.

## string-semantics

- Status: `conditional`
- Strategy: `strict-ecmascript-string-value-contract`
- Evidence: `certification/local-holdout-evidence.json`, `certification/module-equivalence.json`
- Reason: JavaScript and TypeScript share the pinned ECMAScript string value, strict equality, and concatenation model; the independent string corpus is still required.

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
