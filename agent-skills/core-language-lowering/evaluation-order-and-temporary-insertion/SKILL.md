---
name: evaluation-order-and-temporary-insertion
description: Preserve receiver, operand, argument, property, index, await, and short-circuit evaluation order by inserting scoped temporaries. Use whenever target evaluation behavior may differ or an effectful expression could repeat.
---
# Evaluation Order and Temporary Insertion
Read `../references/lowering-v1.md`. Insert a stable, non-conflicting, source-mapped temporary when target order differs, guards repeat access, capture timing changes, await splits an expression, or exception timing could move. Keep its lifetime in the smallest valid block.

Do not eagerly evaluate lazy operands, move work across locks/effects, or change exception order. Preserve `&&`, `||`, coalesce, optional access and conditional paths. An idiomatic pass may remove a temporary only after re-proving effect count and order.
