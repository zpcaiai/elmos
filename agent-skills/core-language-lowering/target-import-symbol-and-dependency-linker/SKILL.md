---
name: target-import-symbol-and-dependency-linker
description: Bind generated symbols, imports/usings/modules, project references, helpers, compatibility runtimes, and approved external packages. Use after emission or when resolving ambiguous/circular target dependencies.
---
# Target Import, Symbol, and Dependency Linker
Read `../references/lowering-v1.md`. Resolve target type/module maps, standard-library symbols, project references, approved packages, generated helpers, compatibility runtimes and retained-service clients. Distinguish runtime/type-only/static/alias imports and source import side effects.

Handle ESM/CommonJS/exports/extensions, Python absolute/relative/runtime cycles, C# extension/global using/multitarget scopes, and Java static/nested/module/package-private rules. Never install unknown packages, bind by unresolved strings, introduce unapproved module cycles or hide ambiguity. Record all dependency manifest changes.
