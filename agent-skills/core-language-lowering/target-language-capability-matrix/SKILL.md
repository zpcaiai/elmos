---
name: target-language-capability-matrix
description: Build and query version-bound Java, Python, C#, TypeScript, and JavaScript lowering capabilities. Use before selecting any core-language lowering strategy or fallback.
---
# Target Language Capability Matrix
Read `../references/lowering-v1.md`. Inventory all UIR dialect operations and type/control/object/runtime features for the exact target version. Classify each as native, constrained, desugared, helper/runtime/wrapper, agent, manual or unsupported; record preconditions, semantic gaps, fallbacks and rule IDs.

Do not equate similarly named syntax or count preview features by default. Keep JavaScript separate from TypeScript. Missing facts and non-native capabilities without bounded fallback block generation. Persist every capability decision in callable provenance.
