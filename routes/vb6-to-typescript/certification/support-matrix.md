# Support matrix: vb6-to-typescript

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:4979c0f64f88cf8717e1a6f91d2c581459fa4e638b4db00071cf77236dbcbe16`
- Source bytes: `3083`

## type-system

- Status: `experimental`
- Strategy: `deterministic-lowering`
- Evidence: None
- Reason: The typed pure standard-module subset has a local bounded handler; VB6 SP6 compiler/runtime and representative Windows evidence remain NOT\_RUN.

## generics

- Status: `detected-only`
- Strategy: `obligation`
- Evidence: None
- Reason: Generic syntax may be detected, but direction-specific lowering and route execution evidence remain NOT\_RUN.

## nullability

- Status: `detected-only`
- Strategy: `obligation`
- Evidence: None
- Reason: Nullability may be detected, but no direction-specific nullability contract or route execution evidence has been admitted.

## numeric

- Status: `experimental`
- Strategy: `obligation`
- Evidence: None
- Reason: The typed pure standard-module subset has a local bounded handler; VB6 SP6 compiler/runtime and representative Windows evidence remain NOT\_RUN.

## time

- Status: `detected-only`
- Strategy: `obligation`
- Evidence: None
- Reason: Time-related syntax may be detected, but no direction-specific time contract or route execution evidence has been admitted.

## exceptions

- Status: `detected-only`
- Strategy: `obligation`
- Evidence: None
- Reason: Exception syntax may be detected, but no direction-specific exception contract or route execution evidence has been admitted.

## async

- Status: `detected-only`
- Strategy: `obligation`
- Evidence: None
- Reason: Async syntax may be detected, but async behavior has no admitted route profile and route execution remains NOT\_RUN.

## concurrency

- Status: `blocked`
- Strategy: `human-review`
- Evidence: None
- Reason: Concurrency requires a direction-specific semantic contract, runtime campaign, and independent evidence; none has run.

## reflection

- Status: `blocked`
- Strategy: `human-review`
- Evidence: None
- Reason: Reflection requires a direction-specific semantic contract, runtime campaign, and independent evidence; none has run.

## serialization

- Status: `detected-only`
- Strategy: `contract-mapping`
- Evidence: None
- Reason: Serialization boundaries may be detected, but no exact wire contract or route execution evidence has been admitted.

## interop

- Status: `blocked`
- Strategy: `retain-runtime-or-sidecar`
- Evidence: None
- Reason: Interop requires an explicit boundary plan and independently verified runtime evidence; neither has been admitted.
