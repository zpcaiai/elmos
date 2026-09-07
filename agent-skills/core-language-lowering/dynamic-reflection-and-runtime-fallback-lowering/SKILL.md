---
name: dynamic-reflection-and-runtime-fallback-lowering
description: Handle dynamic dispatch, reflection, eval, runtime import/code generation, proxy, metaclass, and opaque UIR nodes safely. Use whenever static lowering cannot prove a closed target.
---
# Dynamic, Reflection, and Runtime Fallback Lowering
Read `../references/lowering-v1.md`. Try static resolution, finite candidate dispatch, adapter, bounded reflection helper, compatibility runtime, retained source service, agent, then manual. Restrict reflection/imports by allowlisted types/members, validated input, audit and explicit errors.

Block user-controlled eval and unrestricted runtime generation. Opaque bodies must fail visibly with `MIGRATION_OPAQUE`, source mapping, semantic summary and blocking obligation—not empty/default code. Agent candidates remain untrusted until static validation and required human review.
