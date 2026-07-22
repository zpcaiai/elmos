---
name: expression-and-operation-lifter
description: Lift executable PSP facts into typed UIR operations while preserving evaluation and sugar. Use for expressions, statements, calls, properties, indexers, lambdas, and structured regions.
---
# Expression and Operation Lifter
Read `../references/uir-v1.md`. Emit ordered operands/results, types, regions, effects, maps, provenance, operator/coercion rules, short-circuit behavior, and reversible sugar hints. Distinguish field/property/indexer and user-defined operators. Unsupported executable semantics become mapped language-opaque operations, never omitted or reconstructed from model guesses.
