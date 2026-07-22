---
name: core-type-mapping-engine
description: Map UIR primitive, user, collection, function, union, structural, generic, numeric, and absence types into a target language. Use for every Batch 5 signature or expression type decision.
---
# Core Type Mapping Engine
Read `../references/lowering-v1.md`. Resolve source-to-target user types first, then primitives, numeric semantics, strings/characters, collections, functions, unions and structural types. Return target syntax/symbol, strategy, conversion need, lossiness and obligations.

Do not turn unknown into Object, Any into Dynamic, Decimal into Double, Python int into an unchecked fixed width, or a union into its first member. Synthesize nominal interfaces/adapters for structural types when safe. Block unrecorded lossy public API mappings and require the target compiler to resolve every emitted type.
