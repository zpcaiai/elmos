---
name: generics-variance-and-structural-type-lowering
description: Lower generic parameters, constraints, variance, wildcards, erasure/reification, higher-kinded and structural types. Use for generic APIs or TypeScript/Python structural contracts crossing into nominal languages.
---
# Generics, Variance, and Structural Type Lowering
Read `../references/lowering-v1.md`. Record parameters, constraints, variance, runtime reification/erasure and defaults. Choose direct generics, wildcard/variance adaptation, synthesized interfaces, type tokens, specialization, guarded erasure, helper or manual strategy.

Never lose constraints, expose a covariant source through a writable target, or use `any` to hide failure. Materialize structural member shapes as nominal interfaces/adapters/guards. Treat mapped/conditional types and reflection-sensitive erasure as explicit obligations; block lossy public generic APIs.
