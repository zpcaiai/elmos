---
name: unified-type-semantics-lifter
description: Lift native PSP types into the UIR semantic type system. Use for signatures, flow narrowing, nullability, structural typing, or numeric preservation.
---
# Unified Type Semantics Lifter
Read `../references/uir-v1.md`. Preserve nominal/structural identity, generics, unions/intersections, callable contracts, declared/inferred/flow types, numeric width/precision/overflow, and distinct null/None/undefined/optional-wrapper absence. Never collapse Any, Unknown, Dynamic, Object, decimal, bigint, or error types. Emit origin/confidence and obligations for target-relevant gaps.
