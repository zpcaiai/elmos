# Support matrix: swift-to-kotlin

Generated from the route's authoritative `../support-matrix.json`; this view does not create execution or certification evidence.

- Source SHA-256: `sha256:9edf729380e1c85ad596f9f7d8f1f6099674e69777624cf20afc071c5bce8c6d`
- Source bytes: `3058`

## type-system

- Status: `experimental`
- Strategy: `deterministic-lowering`
- Evidence: None
- Reason: Analyzer and emitter components are locally available, but no route semantic or target profile is admitted; route execution remains NOT\_RUN.

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

- Status: `detected-only`
- Strategy: `obligation`
- Evidence: None
- Reason: Numeric syntax may be detected, but no direction-specific numeric semantics or route execution evidence has been admitted.

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
