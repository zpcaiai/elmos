---
name: type-symbol-and-call-binding-repair
description: "Repair target type, symbol, namespace, overload, generic, nullability, extension, or adapter bindings. Use for Batch 8 semantic compiler clusters tied to source-target mappings."
---
# Type Symbol and Call Binding Repair
Read `../references/batch-8-repair-loop.md`. Use the UIR type/call model, Batch 5 rule, Batch 6 API map, target compiler Semantic Model and successful neighboring cases. Prefer correcting the mapping rule and regenerating affected code.

Confirm overloads with the target compiler. Do not bind by name alone, silently change public types, hide failures with casts/null-forgiving/dynamic, or collapse structural semantics without an explicit interface/adapter.
