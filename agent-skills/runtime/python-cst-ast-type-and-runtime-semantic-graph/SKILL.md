---
name: python-cst-ast-type-and-runtime-semantic-graph
description: Build Python semantic evidence by combining LibCST, CPython AST, symbol/import/call graphs, mypy or Pyright diagnostics, and bounded runtime traces. Use for semantics-aware Python transformation, dynamic behavior analysis, type-state comparison, monkey-patch detection, or Codemod validation.
---

# Python CST, AST, Type, and Runtime Semantic Graph

## Separate analysis layers

Use LibCST for formatting/comment preservation, metadata, positions, qualified names, scopes, and Codemods. Use CPython AST for syntax, expressions, control flow, async, comprehensions, pattern matching, and compile validation. Do not replace semantic conversion with regex.

Store symbols and edges for imports, dynamic imports, calls, potential calls, inheritance, protocols, decorators, reads/writes, returns, exceptions, awaits, serialization, registration, and monkey patches. Attach source position, stable ID, provenance, and confidence.

Run mypy and Pyright as independent adapters with tool/version/config/diagnostic identity. Never add their error totals together. Compare each tool against its own baseline and report coverage ratios.

## Bound dynamic claims

Trace imports, calls, runtime types, exceptions, plugins, DataFrame schemas, and tensor shapes only inside representative tests/tasks on an approved Runner. State that runtime evidence covers executed paths only. Never infer that unobserved paths do not exist.

Protect generated files. Preserve comments and formatting. Run every Codemod twice in a fresh parse and require no second diff. Emit change attribution and before/after fixtures.

Accept only when CST and AST roles stay distinct, type diagnostics retain tool provenance, dynamic edges carry confidence, runtime coverage is bounded, and Codemods reach a fixpoint.

