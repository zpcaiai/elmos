# Semantic IR Design

## Design goals

- Preserve semantics that cannot be recovered from formatted text alone.
- Support partial and confidence-scored analysis for dynamic languages.
- Keep source-language constructs that have no target equivalent.
- Link every node to source spans, tool version, snapshot, and confidence.
- Allow framework and behavior layers to reference semantic identities.
- Be deterministic and versioned.

## Core model

```text
Module
 ├─ Symbol
 │   ├─ Type
 │   ├─ Function/Method
 │   ├─ Field/Property
 │   └─ Parameter
 ├─ ControlFlowGraph
 ├─ DataFlowGraph
 ├─ EffectSet
 ├─ ErrorModel
 ├─ AsyncModel
 ├─ Ownership/Lifetime Model
 └─ SemanticLoss
```

## Type representation

The type model must express nominal and structural types, union/intersection types, generics, variance, constraints, nullability, optionals, zero values, dynamic/unknown types, value/reference semantics, ownership, layout/ABI, and serialization identity.

## Effects

Effects include state mutation, I/O, database, network, file, clock, randomness, environment, process, secret, logging, event publication, external side effect, synchronization, blocking, cancellation, and unsafe/FFI.

## Errors and absence

The IR must distinguish:

- exception, panic, returned error, status code, sentinel, Result/Either
- null, undefined, nil, None, Option, nullable reference, zero value
- cancellation, timeout, retry exhaustion, and unexpected failure

## Concurrency

The IR models threads, tasks, promises, coroutines, goroutines, channels, actors, event loops, locks, atomics, dispatchers, synchronization contexts, main-thread affinity, happens-before relationships, cancellation, backpressure, and resource lifetime.

## Loss nodes

Unsupported constructs are retained as typed loss nodes:

```json
{
  "code": "DYNAMIC-METHOD-SWIZZLING",
  "severity": "critical",
  "source": {"file": "Example.m", "line": 42},
  "status": "requires-decision",
  "possibleMitigations": ["compatibility-wrapper", "manual-rewrite"]
}
```

A backend may not silently discard a loss node. A readiness gate must treat unresolved critical losses as blockers.
