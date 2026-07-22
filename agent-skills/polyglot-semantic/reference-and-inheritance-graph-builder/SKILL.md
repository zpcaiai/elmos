---
name: reference-and-inheritance-graph-builder
description: Build evidence-backed PSP reference, inheritance, implementation, override, import, annotation, and type-usage graphs. Use after symbol/type recovery or when repository dependency edges need source-level enrichment.
---

# Reference and Inheritance Graph Builder

Read `../references/psp-v1.md` before acting.

Convert native binder facts into declaration, read, write, type-use, import/export, extends, implements, mixes-in, overrides, hides, annotation/decorator, and generic-constraint edges. Bind every edge to a source node/range, resolution level, confidence, and provider method. Use native override rules, substitutions, interface dispatch, extension methods, partial types, prototypes, and Python MRO evidence.

Never infer override or inheritance from names alone. Use candidate or unresolved targets where the environment is incomplete; keep external symbols indexable. Accept only when both endpoints and the evidence node exist, illegal cycles/targets are diagnosed, and exact edges are supported by language authority.
