# Support matrix: go-to-python

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:1d9b6e3bb1f3b9a96eff281e72a21797a28027505b0f8276874e94eb4cfe806d`
- Source bytes: `2643`

## typed-pure-function-v1

- Status: `certified`
- Strategy: `compiler-backed-semantic-ir`
- Evidence: `certification/evidence.json`
- Reason: Certified for typed pure function semantic conversion under the verified typed-pure-function-v1 profile.

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
