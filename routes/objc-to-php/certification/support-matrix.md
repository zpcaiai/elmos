# Support matrix: objc-to-php

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:1455b441f6f186dc505fa3c49444117575b213f59185cba50cedc122dd577e9c`
- Source bytes: `1715`

## typed-pure-function-v1

- Status: `supported`
- Strategy: `compiler-backed-semantic-ir`
- Evidence: `certification/local-development-evidence.json`, `certification/local-holdout-evidence.json`, `certification/local-representative-evidence.json`
- Reason: Supported only inside typed-pure-function-v1 after native analysis, target compilation, separate holdout, and representative behavior replay. Independent and external certification remain NOT\_RUN.

## primitive-types

- Status: `supported`
- Strategy: `exact-type-mapping`
- Evidence: `mappings/types.json`
- Reason: Integer, number, boolean, and string are mapped explicitly in the bounded profile.

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

- Status: `blocked`
- Strategy: `per-function-proof-plus-module-composition`
- Evidence: None
- Reason: This legacy route has not requested the separate module profile.
