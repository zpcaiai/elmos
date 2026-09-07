---
name: python-semantic-adapter
description: Extract Python lossless syntax with LibCST and static semantics with Pyright for PSP v1. Use for Python packages, type stubs, decorators, async code, imports, dynamic calls, and partial type recovery.
---

# Python Semantic Adapter

Read `../references/psp-v1.md` before acting.

Use LibCST for lossless syntax and Pyright for scopes, bindings, imports, types, overloads, protocols, generics, unions, narrowing, call candidates, and diagnostics. Discover environments from Batch 1 metadata without importing modules or executing package code. Model module/class/function/comprehension scopes, `global`, `nonlocal`, decorators, descriptors, `async`/`await`, generators, stubs, namespace packages, and conditional imports.

Keep `Any`, `Unknown`, dynamic attributes, monkey patching, metaclasses, `eval`/`exec`, reflective access, and unresolved imports distinct. An inferred name is not an exact binding; dynamic calls require candidates or runtime-evidence recommendations. Emit PSP core plus Python extensions and explicit type origin/confidence. Accept only when source/CST is lossless, scope semantics are correct, and uncertainty is preserved rather than forced deterministic.
