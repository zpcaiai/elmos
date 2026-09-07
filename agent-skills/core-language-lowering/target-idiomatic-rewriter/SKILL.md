---
name: target-idiomatic-rewriter
description: Reversibly idiomatize a statically verified faithful target body without changing behavior. Use only after Phase A passes and for safe local Java/Python/C#/TypeScript idioms.
---
# Target Idiomatic Rewriter
Read `../references/lowering-v1.md`. Default to Level 1 formatting/naming/local syntax and Level 2 proven constructs; require stronger test evidence for collection/async/error Level 3 and defer architecture Level 4.

Before accepting each rewrite, compare types, effects/count/order, exception and async contracts, collection profile and obligations, then re-run static validation. Never skip finally via early returns, reorder effectful streams/LINQ/comprehensions, merge absence kinds with syntax sugar, or change schedulers. Retain the faithful body as a rollback artifact.
