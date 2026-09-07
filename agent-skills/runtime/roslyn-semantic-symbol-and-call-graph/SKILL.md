---
name: roslyn-semantic-symbol-and-call-graph
description: Use Roslyn Workspace, Compilation, syntax, semantic models, symbols, IOperation, and call analysis to build stable .NET semantic evidence.
---

# Roslyn Semantic, Symbol, and Call Graph

Use Roslyn rather than regular expressions for C# semantic claims.

## Workflow

1. In an approved sandbox, register the matching MSBuild and open the selected solution with `MSBuildWorkspace`; capture workspace diagnostics and the exact configuration.
2. Build each `Compilation`, syntax tree, and semantic model. Record `FULL_COMPILATION`, `PARTIAL_COMPILATION`, `SYNTAX_ONLY`, `METADATA_ONLY`, or `FAILED` honestly.
3. Emit stable symbol IDs from fully qualified symbol identity, kind, project and source provenance.
4. Build declaration/reference/inheritance/implementation/override/type and API-surface edges.
5. Use `IOperation` for invocations, creation, conversions, assignments, async, disposal, locking, throws and dynamic operations.
6. Separate direct, virtual, interface, delegate, event, reflection, DI and dynamic calls; attach confidence instead of inventing a unique target.
7. Inventory generated `.designer.cs`, `.g.cs`, `.generated.cs`, T4, service-reference, EDMX and ResX artifacts. Analyze them but do not modify them by default.

## Transformation rules

Roslyn changes must bind symbols, preserve trivia, format/simplify, create the smallest diff, be idempotent, and record transformation attribution. Partial compilation cannot authorize a semantic rewrite that needs missing types.

## Required output

Produce solution snapshot, symbol/call graphs, API surface, dynamic-call findings, diagnostics, and generated-code inventory with provider/version/method, input hashes, resolution, confidence and source locations.
