---
name: canonical-schema-sql-and-procedure-semantic-model
description: Build vendor-neutral but lossless canonical schema, SQL, and procedure semantic models from Oracle, T-SQL, MySQL, and PostgreSQL syntax. Use for heterogeneous database conversion, dependency graphs, dynamic SQL classification, source-to-target traceability, and semantic compatibility review.
---

# Canonical Database IR

## Parse before converting

- Use Vendor Parser to Vendor AST to Canonical IR to Target AST to Target SQL.
- Never implement heterogeneous conversion with string replacement.
- Model schema, SQL, and procedure language separately and connect them through a dependency graph.
- Retain vendor extensions, source ranges, object identity, and provenance on every canonical node.

## Preserve semantics

- Preserve Oracle empty-string NULL, unbounded NUMBER, DATE time, package state, autonomous transactions, hierarchical queries, and links.
- Preserve SQL Server clustered-index intent, identity, SET options, collation, temp objects, Agent jobs, CLR, and linked servers.
- Preserve MySQL unsigned ranges, enum/set, zero dates, SQL_MODE, case rules, implicit conversions, events, and generated columns.
- Preserve PostgreSQL extensions, search_path, arrays, JSONB, range/domain/enum, volatility, deferrable constraints, and replica identity.
- Represent unsupported or uncertain source constructs as vendor-specific or opaque nodes; do not silently lower them.

## Govern dynamic SQL

- Classify dynamic SQL as PARSED_CONSTANT, PARTIALLY_PARSED, RUNTIME_DEPENDENT, or UNRESOLVED.
- Require runtime trace or human design for tenant-dependent object names, runtime pivots, and unresolved assembly.
- Block target SQL generation when semantic obligations are unknown.

## Emit

- Emit canonical schema, SQL, procedure, dependency, dynamic-SQL, and vendor-semantic artifacts with bidirectional source/target traceability.
