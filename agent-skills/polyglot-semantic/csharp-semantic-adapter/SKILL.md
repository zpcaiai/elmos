---
name: csharp-semantic-adapter
description: Extract authoritative C# syntax and semantics with Roslyn for PSP v1. Use for .NET solutions/projects, multi-target frameworks, partial types, generics, async, LINQ, overload resolution, and source-generator risk.
---

# C# Semantic Adapter

Read `../references/psp-v1.md` before acting.

Use pinned Roslyn SyntaxTree, Compilation, SemanticModel, Symbol APIs, and IOperation through the isolated native analyzer port. Construct compilations per target framework from Batch 1 metadata without running source generators or loading unknown analyzers. Preserve namespaces, aliases, nullable context, partial declarations, records, structs, delegates, events, properties, generics, variance, constraints, extension methods, overload selection, virtual/interface dispatch, pattern matching, LINQ, and async semantics.

Merge partial types under one symbol with multiple declaration sites, but never merge different target-framework semantics. Diagnose missing metadata, generated symbols, `dynamic`, reflection, DLR, COM, and framework activation. Emit PSP core plus C# extensions. Accept only when Roslyn-selected bindings are traceable, partial sites remain mapped, and target framework identity is explicit.
