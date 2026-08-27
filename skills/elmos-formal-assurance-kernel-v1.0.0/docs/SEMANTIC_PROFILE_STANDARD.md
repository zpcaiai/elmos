# Semantic Profile Standard

A Semantic Profile defines exactly which language/runtime behaviors Elmos can reason about.

## Mandatory dimensions

- syntax and type-system subset;
- integer width, overflow and shift semantics;
- floating-point and decimal semantics;
- null/option/missing values;
- strings, Unicode indexing and normalization;
- collection equality and iteration order;
- object identity, heap and aliasing;
- exceptions and cleanup/finally/defer;
- async/cancellation and concurrency memory model;
- time, randomness and environment;
- serialization and wire compatibility;
- reflection, code generation, macros and dynamic loading;
- FFI/native/unsafe behavior;
- compiler flags and runtime version;
- undefined/unspecified behavior policy.

## Feature states

```text
VERIFIED
BOUNDED
RUNTIME_MONITORED
UNSUPPORTED
```

Every encountered feature is classified. “Mostly supported” is not a machine state.

## Compatibility

Profiles are semantically versioned. A change that alters program meaning or proof interpretation increments the major version and invalidates dependent evidence. Compiler/runtime patch changes are TCB changes even when the profile version is unchanged.

## Conversion rule

A source feature may map to a target feature only when the relation is encoded and discharged, or when the result is explicitly downgraded to a bounded/runtime/unsupported boundary.
