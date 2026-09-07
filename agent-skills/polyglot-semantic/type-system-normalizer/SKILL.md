---
name: type-system-normalizer
description: Convert native Java, Python, C#, and JavaScript/TypeScript type facts into PSP v1 Type records without erasing language semantics. Use for recovered types, nullability, generics, unions, callable signatures, and type-confidence reporting.
---

# Type System Normalizer

Read `../references/psp-v1.md` before acting.

Normalize primitive, nominal, structural, generic, type-variable, union, intersection, tuple, callable, array, literal, nullable, dynamic, unknown, error, and never/bottom kinds. Preserve canonical/display names, arguments, members, return/parameter types, nullability, mutability, origin, confidence, and language extensions. Record compiler/type-checker, annotation, stub, flow inference, syntax inference, heuristic, runtime unknown, and unresolved origins distinctly.

Do not equate Java primitive/wrapper, C# value/reference type, Python `Any`/`Unknown`, or TypeScript `any`/`unknown`; do not choose target-language mappings in Batch 2. Deduplicate only canonical-equivalent native types. Every symbol/type relation must resolve, recursive types must be representable by IDs, and lost distinctions must become diagnostics.
