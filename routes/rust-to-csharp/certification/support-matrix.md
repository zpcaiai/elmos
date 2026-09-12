# Support matrix: rust-to-csharp

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:687306a6a8ef40ec69e302079b3358f18b7d44d6132ca4a91dae05ca90f068bc`
- Source bytes: `2663`

## typed-pure-function-v1

- Status: `supported`
- Strategy: `compiler-backed-semantic-ir`
- Evidence: `certification/evidence.json`
- Reason: Bounded local evidence supports typed pure function semantic conversion under the verified typed-pure-function-v1 profile.

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
