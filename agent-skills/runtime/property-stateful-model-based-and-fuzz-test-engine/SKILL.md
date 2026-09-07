---
name: property-stateful-model-based-and-fuzz-test-engine
description: Generate replayable property, stateful, model-based, metamorphic, and bounded fuzz tests from types, schemas, contracts, state machines, and business invariants. Use for boundary discovery, sequence failures, weak oracles, or parser/protocol robustness.
---

# Property, Stateful, Model-based, and Fuzz Testing

## Derive valid properties

Start from business or mathematical invariants. Support round-trip, idempotency, commutativity, associativity, invariant, monotonicity, bounds, equivalence, metamorphic, state-transition, and no-crash properties. Keep concrete business examples; property tests do not replace them.

## Build controlled generators

Derive domains from types, schemas, OpenAPI, Protobuf, JSON Schema, database constraints, domain rules, summarized distributions, or human rules. Cover valid, boundary, and invalid values. Record provider, seed, generator version, limits, and input hashes. Never generate real sensitive data.

## Test state and models

Define state, actions, preconditions, transitions, postconditions, and invariants. Compare a simple reference model to the system under test. Shrink failures to minimal examples and minimal action sequences, and make every failure replayable.

## Bound fuzzing

Distinguish property-guided, schema-guided, parser, protocol, and security fuzzing. Enforce rate, size, timeout, side-effect, network, and resource limits. Preserve the minimized failing input and execution evidence. Run only inside an approved isolated runner.
