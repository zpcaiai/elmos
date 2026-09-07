---
name: java-semantic-adapter
description: Extract authoritative Java syntax, scopes, symbols, types, references, inheritance, calls, and control-flow facts for PSP v1. Use for Maven/Gradle Java modules, including generics, overloads, records, sealed types, and reflection risk.
---

# Java Semantic Adapter

Read `../references/psp-v1.md` before acting.

Use pinned Eclipse JDT, Javac, JavaParser Symbol Solver, or OpenRewrite LST through the isolated native analyzer port. Build the classpath/module path from Batch 1 without running builds or annotation processors. Preserve packages, nested/local/anonymous types, records, sealed hierarchies, generics, wildcards, intersection types, annotations, overload selection, constructors, static/virtual/interface dispatch, overrides, exceptions, lambdas, method references, and source mappings.

Keys must distinguish qualified owner, member name, erased/full parameter types, return type where needed, and module/project. Record compiler-selected facts at confidence 1.0; incomplete classpaths, reflection, proxies, generated members, Lombok-like processors, and framework-managed entry points remain diagnosed or candidate-based. Emit PSP core plus Java extensions; pass only when authoritative bindings are traceable and unresolved inputs are explicit.
