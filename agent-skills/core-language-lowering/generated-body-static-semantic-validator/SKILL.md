---
name: generated-body-static-semantic-validator
description: Validate generated bodies with target parser, compiler/type checker, binding model, and UIR semantic invariants. Use before every faithful patch, idiomatic rewrite, or agent candidate is accepted.
---
# Generated Body Static Semantic Validator
Read `../references/lowering-v1.md`. Reparse for the exact version, bind all symbols/overloads/generics/imports, check assignment/return/nullability/exhaustiveness/narrowing/reachability/definite assignment, then compare effects, evaluation order, exceptions, async, collections, cleanup and obligations.

Use javac/build compiler, Python parse plus Pyright, Roslyn Compilation, TypeScript Program/TypeChecker, or JavaScript checkJs/JSDoc policy. Preserve raw diagnostics linked to UIR. Do not suppress errors or unreported any/dynamic/Object downgrade. State clearly that static readiness is not behavioral equivalence.
