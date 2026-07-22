---
name: collection-iteration-and-query-lowering
description: Lower arrays, lists, sets, maps, iterables, streams, LINQ, generators, comprehensions, and query pipelines while preserving collection semantics. Use for every collection or iteration operation.
---
# Collection, Iteration, and Query Lowering
Read `../references/lowering-v1.md`. Profile shape, order, sorting, uniqueness, mutability, laziness, replayability, thread safety, null elements, equality/hash and backpressure. Prefer an explicit faithful loop for effects, short circuiting or uncertain iteration; use pipelines only after purity/order/laziness/error proof.

Do not silently materialize, reorder, parallelize, turn list into set, lose ordered maps, change missing-key behavior or reuse a single-consumption stream. Record memory/performance obligations for necessary materialization and test output order.
