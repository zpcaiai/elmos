---
name: repository-call-graph-builder
description: Build a conservative repository call graph with exact, candidate, dynamic, reflective, framework-managed, and unresolved call resolution. Use after symbols/types for dispatch, async, entry-point, and translation-risk analysis.
---

# Repository Call Graph Builder

Read `../references/psp-v1.md` before acting.

Create one call-site entity per invocation and separate call edges to compiler-selected or bounded candidate targets. Preserve caller, syntax node, hashed expression, dispatch kind, declared target, receiver/argument/return types, async behavior, resolution, confidence, and native evidence. Model static/direct, virtual, interface, constructor, extension, delegate/function-value, closure, dynamic, reflective, and framework-managed dispatch.

For Java/C#, expand candidates only from proven hierarchy/override facts. For Python/JavaScript, use type-checker evidence and bounded flow facts; otherwise mark dynamic. Record awaited, spawned, callback, promise/task, generator, and event-handler relationships. Never create exact edges from text matching. All edges must reference an existing call site, caller, and target; coverage must report exact/candidate/dynamic/unresolved separately.
