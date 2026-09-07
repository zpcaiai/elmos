---
name: control-flow-lowering-and-structurizer
description: Lower UIR structured control flow and CFG into target if/switch/match/loops/try/jumps while preserving every edge and abrupt exit. Use for any callable with branching, loops, cleanup, labels, fallthrough, or irreducible flow.
---
# Control Flow Lowering and Structurizer
Read `../references/lowering-v1.md`. Prefer the source structure, then an equivalent target construct, structured rewrite, helper extraction, and finally an explicit state machine. Recover natural loops/if/switch regions from reducible CFGs before handling irreducible regions.

Preserve Python loop-else, Java labels, JavaScript fallthrough, pattern bindings, return/throw/break/continue targets and all finally paths. Never delete unreachable code without provenance or introduce arbitrary goto. Mark state machines low-idiom and obligations for exhaustiveness changes.
