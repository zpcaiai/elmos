---
name: cross-language-symbol-table-builder
description: Normalize authoritative native declarations and scopes into the PSP v1 cross-language symbol table. Use after language adapters or whenever symbol identity, shadowing, partial declarations, or unresolved references must be reconciled.
---

# Cross-language Symbol Table Builder

Read `../references/psp-v1.md` before acting.

Create repository/module/namespace/package/type/callable/block/comprehension scopes and preserve lexical ownership, visibility, modifiers, annotations, signatures, declaration sites, and native keys. Give declarations stable language/project/native-key IDs; include enclosing callable and range for locals; create explicit unresolved IDs only when evidence cannot bind a target. Merge only authority-proven partial declarations and never merge by simple name across modules or languages.

Apply imports, aliases, shadowing, `global`/`nonlocal`, nested types, overload sets, extension methods, prototypes, and generated/test flags according to native semantics. Every symbol must reference an existing scope and type and at least one valid declaration site unless it is explicitly external/unresolved. Emit scopes, symbols, external dependencies, and binding diagnostics.
